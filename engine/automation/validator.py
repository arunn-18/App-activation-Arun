"""v2 validator: pure code, no LLM.

Takes a (possibly partial) extracted spec + the conversation text and decides:
  - errors:      illegal vocabulary / incompatible combos (extraction bug or bad map)
  - hallucinated: filled values with no source in the user's own words -> slot is
                  emptied and re-asked; the model never gets to invent a name
  - missing:     required slots still empty -> each maps to a planned question
  - unsupported: asks we recognize but don't build -> called out, never faked
  - status:      "complete" | "needs_info" | "invalid"

Question planning: bundle at most MAX_QUESTIONS per turn, ordered trigger ->
scope/conditions -> action params. The loop keeps asking until nothing is missing.

apps_ws (optional): the connected_apps.py fixture, re-checked against a
connector action's chosen recipe's prerequisites (e.g. is Salesforce actually
connected?). None skips the check — see the connector prerequisites block.
"""
import re
import connected_apps
import workspace as wsmod

from . import schema

MAX_QUESTIONS = 3

ENTITY_WORD = {"tag": "tag", "user": "teammate", "inbox": "shared inbox"}
ENTITY_LISTS = {"tag": "tags", "user": "agents", "inbox": "shared_inboxes"}
ENTITY_OTHER_HINT = {"tag": "A different tag", "user": "Someone else",
                     "inbox": "A different inbox"}


def _entity_options(ws, kind):
    """Workspace entities as pick-one options for a choice question. Picked
    values are canonical workspace names, so they resolve as 'exact' when the
    composed chat answer round-trips through extraction."""
    if not ws or kind not in ENTITY_LISTS:
        return []
    ents = ws.get(ENTITY_LISTS[kind], [])
    return [{"label": wsmod.canonical(kind, e) if kind == "tag"
             else wsmod.label(kind, e),
             "value": wsmod.canonical(kind, e)} for e in ents]

TRIGGER_QUESTION = ("When should this run — when a **new** conversation arrives, when a "
                    "**reply** comes in on an existing one, or when **we send** an email?")
SCOPE_QUESTION = ("Should this run on **every** matching conversation, or only some? If it's "
                  "a subset, tell me what to match — the senders or the subject/body keywords.")

# Structured option sets for choice questions. `value` is the literal text a UI
# composes into the user's chat message when picked — answers always travel
# through the conversation, never as a side channel (provenance depends on it).
TRIGGER_OPTIONS = [
    {"label": "When a new conversation arrives", "value": "when a new conversation arrives"},
    {"label": "When a reply comes in on an existing one",
     "value": "when a reply comes in on an existing conversation"},
    {"label": "When we send an email", "value": "when we send an email"},
]
SCOPE_OPTIONS = [
    {"label": "Every matching conversation", "value": "run it on every matching conversation"},
]


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _in_convo(value, convo_norm):
    v = _norm(value)
    return bool(v) and v in convo_norm


# Mechanism-language that describes HOW to match, never WHAT to match. Users echo
# these from our own scope question ("match specific senders") — they are not values.
META_VALUES = {"specific senders", "specific sender", "certain senders", "some senders",
               "senders", "sender", "keywords", "keyword", "specific keywords",
               "subject keywords", "body keywords", "certain keywords", "specific emails"}

# Whole-scope statements for the scope pin below. Kept tight: each phrase is an
# unambiguous "run it on all of it" answer, not any sentence containing "every"
# ("assign every new incoming email to john" must not match). The first entry is
# the exact text the scope question's choice composes into chat.
# Placeholder text for free-text condition questions — a concrete example beats
# an abstract prompt, and the questionnaire input needs something to show.
TEXT_HINTS = {
    "from": "sender address, e.g. invoice@acme.com",
    "to": "recipient address, e.g. support@brightpath.example",
    "cc": "cc'd address",
    "bcc": "bcc'd address",
    "reply_to": "reply-to address",
    "from_domain": "sender domain, e.g. acme.com",
    "to_domain": "recipient domain",
    "reply_to_domain": "reply-to domain",
    "subject": "subject keywords, e.g. invoice",
    "body": "body keywords",
}

EVERYTHING_PHRASES = ("every matching conversation", "on everything",
                      "on every conversation", "on all conversations",
                      "all of them", "no conditions")


def _resolve_entity(ws, kind, v, slot, missing, resolutions, entity_notes):
    """Existence/ambiguity resolution for one workspace entity value, shared by
    action params and entity conditions (tag/assignee) so both behave the same:
    exact -> canonicalize, unique fuzzy -> resolve and disclose, ambiguous ->
    ask, unknown -> did-you-mean or a create-first note."""
    r = wsmod.RESOLVERS[kind](ws, v)
    if r["status"] == "exact":
        can = wsmod.canonical(kind, r["matches"][0])
        if can != v:  # fix casing/spelling to the workspace's
            resolutions.append({"slot": slot, "value": v, "canonical": can})
    elif r["status"] == "resolved":
        # unique fuzzy match: resolve and disclose, don't ask
        # (over-asking evidence: v2 first run) — ambiguous still asks
        ent = r["matches"][0]
        resolutions.append({"slot": slot, "value": v,
                            "canonical": wsmod.canonical(kind, ent),
                            "detail": wsmod.label(kind, ent)})
    elif r["status"] == "ambiguous":
        opts = " / ".join(wsmod.label(kind, m) for m in r["matches"])
        missing.append({"slot": slot, "value": v, "question":
                        f"'{v}' matches more than one {ENTITY_WORD[kind]}: "
                        f"{opts}. Which one?",
                        "kind": "choice", "options": [
                            {"label": wsmod.label(kind, m),
                             "value": wsmod.canonical(kind, m)}
                            for m in r["matches"]]})
    elif kind == "tag":
        # unknown tag: near-miss -> did-you-mean; else buildable with a
        # create-first note (typos shouldn't silently become new tags)
        cands = wsmod.suggest(ws, kind, v)
        if cands:
            missing.append({
                "slot": slot, "value": v, "kind": "choice",
                "question": (f"There's no tag '{v}' — did you mean "
                             + " or ".join(f"'{c}'" for c in cands) + "?"),
                "options": [{"label": c, "value": c} for c in cands]
                + [{"label": f"No — create '{v}' as a new tag",
                    "value": f"create a new tag called {v}"}],
            })
        else:
            entity_notes.append(f"Tag '{v}' doesn't exist in this workspace yet — "
                                "create it first, then this rule can apply it.")
    else:
        cands = wsmod.suggest(ws, kind, v)
        opts = [{"label": wsmod.label(kind, c),
                 "value": wsmod.canonical(kind, c)} for c in cands]
        missing.append({
            "slot": slot, "value": v,
            "question": (f"I can't find a {ENTITY_WORD[kind]} matching '{v}' in "
                         "this workspace — "
                         + ("did you mean "
                            + " or ".join(f"'{o['value']}'" for o in opts) + "?"
                            if opts else "which one should it be?")),
            **({"kind": "choice", "options": opts, "allow_other": True,
                "other_hint": ENTITY_OTHER_HINT[kind]} if opts else {}),
        })


def validate(spec, conversation_text, ws=None, user_messages=None, apps_ws=None):
    convo_norm = _norm(conversation_text)
    errors, missing, hallucinated = [], [], []
    resolutions, entity_notes, assumptions = [], [], []
    unsupported = list(spec.get("unsupported_requests") or [])

    # ---- pilot scope: declare what this build won't do, and drop it from the
    # rule rather than building something the footer says isn't covered
    out_of_scope = []
    if schema.PILOT_SCOPE:
        if (spec.get("ai_extract") or {}).get("variables"):
            out_of_scope.append("ai")
            unsupported.append(schema.OUT_OF_SCOPE["ai"])
        if any(c.get("property") in schema.TIME_PROPERTIES
               for g in (spec.get("condition_groups") or []) for c in g):
            out_of_scope.append("time")
            unsupported.append(schema.OUT_OF_SCOPE["time"])

    # ---- AI extraction variables
    ai_vars = {}  # name -> variable dict
    for vi, var in enumerate([] if "ai" in out_of_scope
                             else (spec.get("ai_extract") or {}).get("variables") or []):
        name, vtype = var.get("name"), var.get("type")
        where = f"ai variable {vi + 1}"
        if not name:
            errors.append(f"{where}: has no name")
            continue
        if name in ai_vars:
            errors.append(f"{where}: duplicate name '{name}'")
            continue
        ai_vars[name] = var
        if vtype not in schema.AI_VARIABLE_TYPES:
            errors.append(f"{where} '{name}': unknown type '{vtype}' "
                          f"(allowed: {', '.join(schema.AI_VARIABLE_TYPES)})")
        if vtype == "single_select":
            options = var.get("options") or []
            if not options:
                missing.append({"slot": f"ai_extract.variables[{vi}].options",
                                "question": f"What are the possible values the AI should "
                                            f"choose between for '{name}'?"})
            for o in options:
                # option labels are user vocabulary, like tags: provenance applies
                if not _in_convo(o, convo_norm):
                    hallucinated.append({"slot": f"ai_extract.variables[{vi}].options",
                                         "value": o,
                                         "question": f"What are the possible values for '{name}'?"})

    # ---- trigger
    trigger = spec.get("trigger")
    if not trigger:
        missing.append({"slot": "trigger", "question": TRIGGER_QUESTION,
                        "kind": "choice", "options": TRIGGER_OPTIONS})
    elif trigger not in schema.TRIGGERS:
        errors.append(f"unknown trigger '{trigger}'")

    # ---- scope pin: an explicit "run it on everything" answer beats conditions
    # re-derived from EARLIER messages. Provenance guards every value in the
    # spec, but scope is the ABSENCE of conditions — this is its guard. Without
    # it, per-turn re-extraction can quietly contradict an answered question
    # (observed: "route jade's mail" -> answer "every matching conversation" ->
    # next turn resurrects `to contains jade`). A condition whose value first
    # appears AFTER the everything-answer supersedes the pin: the user changed
    # their mind, and that later message wins instead.
    groups = [[c for c in g
               if not ("ai" in out_of_scope and c.get("property") == "ai_variable")
               and not ("time" in out_of_scope
                        and c.get("property") in schema.TIME_PROPERTIES)]
              for g in (spec.get("condition_groups") or [])]
    groups = [g for g in groups if g]
    scope_pinned = False
    if groups and user_messages and not any(
            c.get("property") == "ai_variable" for g in groups for c in g):
        msgs_norm = [_norm(m) for m in user_messages]
        vals = [_norm(v) for g in groups for c in g
                for v in (c.get("values") or []) if _norm(v)]

        def _pure_everything(m):
            # a whole-scope statement that contributes no condition value itself
            if m != "everything" and not any(p in m for p in EVERYTHING_PHRASES):
                return False
            return not any(v in m for v in vals)

        last = max((i for i, m in enumerate(msgs_norm) if _pure_everything(m)),
                   default=None)
        if last is not None and not any(v in m for v in vals
                                        for m in msgs_norm[last + 1:]):
            dropped = "; ".join(
                f"{schema.PROPERTY_LABELS.get(c.get('property'), c.get('property'))}"
                f" {c.get('op')} "
                + ", ".join(f"'{v}'" for v in (c.get("values") or []))
                for g in groups for c in g)
            entity_notes.append(
                f"You said to run this on every matching conversation, so I "
                f"dropped a condition it had picked up ({dropped.strip()}). "
                f"Say if you want it back.")
            scope_pinned = True
            groups = []

    # ---- conditions
    for gi, group in enumerate(groups):
        for ci, cond in enumerate(group):
            prop, op = cond.get("property"), cond.get("op")
            where = f"condition {gi + 1}.{ci + 1}"
            pspec = schema.CONDITION_PROPERTIES.get(prop)
            if pspec is None:
                errors.append(f"{where}: unknown property '{prop}'")
                continue
            if op not in pspec["ops"]:
                errors.append(f"{where}: operator '{op}' not valid for '{prop}' "
                              f"(allowed: {', '.join(pspec['ops'])})")
            if trigger in schema.TRIGGERS:
                ce = schema.compat_error(trigger, prop)
                if ce:
                    errors.append(f"{where}: {ce}")
            values = cond.get("values") or []
            if pspec["kind"] == "ai":
                vname = cond.get("variable")
                var = ai_vars.get(vname)
                if not vname:
                    errors.append(f"{where}: ai_variable condition names no variable")
                    continue
                if var is None:
                    errors.append(f"{where}: references undeclared AI variable '{vname}'")
                    continue
                vtype = var.get("type")
                if vtype == "boolean" and op in ("exists", "does_not_exist"):
                    # a boolean always gets a value, so presence == truth; normalize
                    # to the encoding prod rules actually use (no boolean-exists in
                    # the 90d dump — assumption flagged, like the AND/OR semantics)
                    cond["op"] = "is"
                    cond["values"] = ["true" if op == "exists" else "false"]
                    continue
                if op in ("exists", "does_not_exist"):
                    continue  # presence tests need no values
                if vtype == "boolean":
                    for v in values:
                        if _norm(v) not in ("true", "false"):
                            errors.append(f"{where}: boolean '{vname}' can only be "
                                          f"true/false, got '{v}'")
                    if not values:
                        missing.append({"slot": f"condition_groups[{gi}][{ci}].values",
                                        "question": f"Should this fire when '{vname}' is "
                                                    f"true, or when it's false?",
                                        "kind": "choice", "options": [
                                            {"label": "When it's true",
                                             "value": f"fire when {vname} is true"},
                                            {"label": "When it's false",
                                             "value": f"fire when {vname} is false"}]})
                elif vtype == "single_select":
                    options = var.get("options") or []
                    for v in values:
                        if options and v not in options:
                            errors.append(f"{where}: '{v}' is not an option of '{vname}' "
                                          f"(options: {', '.join(options)})")
                    if not values:
                        missing.append({"slot": f"condition_groups[{gi}][{ci}].values",
                                        "question": f"Which '{vname}' value(s) should "
                                                    f"trigger the actions?",
                                        "kind": "choice", "multiple": True,
                                        "options": [{"label": o, "value": o}
                                                    for o in options]})
                elif not values:
                    missing.append({"slot": f"condition_groups[{gi}][{ci}].values",
                                    "question": f"What value of '{vname}' should this "
                                                f"match?"})
                continue
            if pspec["kind"] == "enum":
                for v in values:
                    if v not in pspec["values"]:
                        errors.append(f"{where}: '{v}' is not a valid {prop} value "
                                      f"(allowed: {', '.join(pspec['values'])})")
            elif pspec["kind"] == "entity":
                # tag/assignee conditions name workspace entities, so they get
                # the SAME treatment as entity action params: provenance first,
                # then existence/ambiguity resolution against the workspace.
                slot = f"condition_groups[{gi}][{ci}].values"
                label = schema.PROPERTY_LABELS.get(prop, prop)
                ekind = pspec["entity"]
                if not values:
                    entry = {"slot": slot,
                             "question": f"Which {ENTITY_WORD[ekind]}(s) should "
                                         f"the {label} condition match?"}
                    opts = _entity_options(ws, ekind)
                    if opts:
                        entry.update({"kind": "choice", "options": opts,
                                      "multiple": op in ("is_any_of", "is_all_of",
                                                         "is_none_of"),
                                      "allow_other": True,
                                      "other_hint": ENTITY_OTHER_HINT[ekind]})
                    missing.append(entry)
                for v in values:
                    if not _in_convo(v, convo_norm):
                        src = (wsmod.verified_source(ws, ekind, v, conversation_text)
                               if ws else None)
                        if src:
                            resolutions.append({"slot": slot, "value": src,
                                                "canonical": v})
                            continue
                        hallucinated.append({
                            "slot": slot, "value": v, "entity": ekind,
                            "question": f"Which {ENTITY_WORD[ekind]}(s) should the "
                                        f"{label} condition match?"})
                        continue
                    if ws:
                        _resolve_entity(ws, ekind, v, slot, missing, resolutions,
                                        entity_notes)
            elif pspec["kind"] in ("text", "address"):
                # builder vocabulary in the question, and a hint the input box can
                # use as its placeholder — "Something else" only makes sense as an
                # escape hatch beside choices, never as a bare text prompt
                label = schema.PROPERTY_LABELS.get(prop, prop)
                hint = TEXT_HINTS.get(prop, "the text to match")
                if not values:
                    missing.append({"slot": f"condition_groups[{gi}][{ci}].values",
                                    "question": f"What should {label} match?",
                                    "other_hint": hint})
                for v in values:
                    if not _in_convo(v, convo_norm) or _norm(v) in META_VALUES:
                        hallucinated.append({"slot": f"condition_groups[{gi}][{ci}].values",
                                             "value": v, "other_hint": hint,
                                             "question": f"What exactly should {label} match?"})

    # ---- coherence: AND'd groups that constrain the same single-valued header
    # with values that can't coexist make a rule that never fires. Legal by the
    # schema, dead in reality — usually the user meant a SECOND automation
    # ("also, when it comes from billing@…"). Ask, don't guess.
    SINGLE_VALUED = ("from", "from_domain", "reply_to", "reply_to_domain")
    prop_groups = {}
    for group in groups:
        props = {c.get("property") for c in group}
        if len(props) == 1:
            p = next(iter(props))
            if p in SINGLE_VALUED and all(c.get("op") in ("is", "contains")
                                          for c in group):
                vals = [_norm(v) for c in group for v in (c.get("values") or []) if v]
                if vals:
                    prop_groups.setdefault(p, []).append(vals)
    for p, vgroups in prop_groups.items():
        if len(vgroups) < 2:
            continue
        a, b = vgroups[0], vgroups[1]
        # satisfiable when a value pair nests (e.g. 'acme.com' within
        # 'invoice@acme.com'); otherwise both can never hold at once
        if any(x in y or y in x for x in a for y in b):
            continue
        label = schema.PROPERTY_LABELS.get(p, p)
        missing.append({
            "slot": "conflict:conditions",
            "question": (f"An email's {label} can't match both '{a[0]}' and "
                         f"'{b[0]}' at the same time, so this rule would never "
                         f"fire. Should these be two separate automations?"),
            "kind": "choice",
            "options": [
                {"label": "Two separate automations — keep this one as it was; "
                          "I'll set up the second next",
                 "value": f"make these two separate automations - keep this rule "
                          f"for {a[0]} as it was, and I'll set up the {b[0]} one "
                          f"separately after this"},
                {"label": f"One rule matching either '{a[0]}' or '{b[0]}'",
                 "value": "one rule that matches either of them"},
            ],
        })
        break  # one structural question at a time

    # ---- coherence: a rule assigns/sets status once; duplicates overwrite
    for atype, pick in (("assign", lambda a: a.get("target")),
                        ("status", lambda a: a.get("status_value"))):
        dupes = [pick(a) for a in (spec.get("actions") or [])
                 if a.get("type") == atype and pick(a)]
        if len(dupes) > 1:
            noun = "assign" if atype == "assign" else "set the status"
            missing.append({
                "slot": f"conflict:actions.{atype}",
                "question": (f"This rule would {noun} twice "
                             f"({' then '.join(repr(d) for d in dupes)}) — only the "
                             f"last one sticks. How should it be?"),
                "kind": "choice",
                "options": [
                    {"label": "Two separate automations — keep this one as it "
                              "was; I'll set up the second next",
                     "value": "make these two separate automations - keep this "
                              f"rule with {dupes[0]} as it was, and I'll set up "
                              "the other one separately after this"},
                ] + [{"label": f"Keep only {d!r}", "value": f"keep only {d}"}
                     for d in dupes[:3]],
            })

    # ---- scope: no conditions and no explicit all-mail statement -> ASSUMPTION,
    # not a blocking question. A trigger + action with no conditions is a legal
    # rule; nothing is missing — one reading (run on everything) was chosen for
    # the user. Blocking questions are reserved for slots without which no legal
    # rule exists ("which tag?"). The assumption is surfaced on the draft and
    # confirmed at apply time; answering in chat ("only emails from acme.com" /
    # "run it on everything") converts it to specified either way.
    if trigger and not groups and not spec.get("scope_confirmed") and not scope_pinned:
        assumptions.append({
            "slot": "scope",
            "assumed": "everything",
            "summary": "runs on every matching conversation",
            "question": SCOPE_QUESTION,
        })

    # ---- actions
    actions = spec.get("actions") or []
    if not actions:
        missing.append({"slot": "actions",
                        "question": "What should happen when this fires — tag, assign, "
                                    "change status, add a note, send a reply...?"})
    for ai, action in enumerate(actions):
        atype = action.get("type")
        aspec = schema.ACTIONS.get(atype)
        if aspec is None:
            if atype in schema.UNSUPPORTED:
                unsupported.append(schema.UNSUPPORTED[atype])
            else:
                errors.append(f"action {ai + 1}: unknown type '{atype}'")
            continue
        for pname, p in aspec["params"].items():
            val = action.get(pname)
            vals = val if isinstance(val, list) else ([val] if val not in (None, "") else [])
            if p.get("required") and len(vals) < p.get("min", 1):
                entry = {"slot": f"actions[{ai}].{pname}", "question": p["question"]}
                if p.get("enum"):
                    entry["kind"] = "choice"
                    labels = p.get("enum_labels") or {}
                    # value is what a picked option composes into chat, so it
                    # must read as real user text — the human label when one
                    # exists (a raw enum id like a recipe id never should),
                    # else the enum value itself (already human words, e.g.
                    # STATUS_VALUES).
                    entry["options"] = [{"label": labels.get(v, v), "value": labels.get(v, v)}
                                        for v in p["enum"]]
                else:
                    # entity slots: offer what the workspace actually has (the
                    # Amplitude agent-setup pattern), with a free-text lane
                    opts = _entity_options(ws, p.get("entity"))
                    if opts:
                        entry.update({"kind": "choice", "options": opts,
                                      "multiple": bool(p.get("list")),
                                      "allow_other": True,
                                      "other_hint": ENTITY_OTHER_HINT[p["entity"]]})
                missing.append(entry)
                continue
            if p.get("enum"):
                for v in vals:
                    if v not in p["enum"]:
                        errors.append(f"action {ai + 1}: '{v}' not in {p['enum']}")
                # non-vocabulary enums (the assign_among distribution method) are
                # never stated verbatim, so plain provenance can't guard them.
                # Require a supporting PHRASE, else ask rather than assume — the
                # builder makes you choose, and so must we.
                pe = p.get("provenance_enum")
                if pe and vals:
                    ok = any(ph in convo_norm
                             for v in vals for ph in pe.get(v, []))
                    if not ok:
                        action[pname] = None
                        missing.append({"slot": f"actions[{ai}].{pname}",
                                        "question": p["question"],
                                        "kind": "choice",
                                        "options": [{"label": lbl, "value": lbl}
                                                    for lbl in ("round robin",
                                                                "load balancing")]})
                        continue
            kind = p.get("entity")
            bad_vals = set()
            if p.get("provenance"):
                for v in vals:
                    if _norm(v) == "unassign":
                        continue
                    if _in_convo(v, convo_norm):
                        continue
                    # not in the user's words: with a workspace, the model may have
                    # canonicalized via a tool lookup — accept ONLY if code re-runs
                    # the resolution from the user's own words and lands on v.
                    src = (wsmod.verified_source(ws, kind, v, conversation_text)
                           if ws and kind else None)
                    if src:
                        resolutions.append({"slot": f"actions[{ai}].{pname}",
                                            "value": src, "canonical": v})
                        continue
                    bad_vals.add(_norm(v))
                    hallucinated.append({"slot": f"actions[{ai}].{pname}", "value": v,
                                         "question": p["question"], "entity": kind})
            # entity existence/ambiguity checks against the workspace
            if ws and kind:
                for v in vals:
                    if _norm(v) in bad_vals or _norm(v) == "unassign":
                        continue
                    _resolve_entity(ws, kind, v, f"actions[{ai}].{pname}",
                                    missing, resolutions, entity_notes)

    # ---- connector: recipe prerequisites -------------------------------------
    # Recipe EXISTENCE and the "recipe id is required, non-inferred vocabulary"
    # check both fall out of the generic required/enum machinery above for
    # free (recipe is just another ACTIONS param with an enum) — this block
    # only adds what's specific to connectors: re-verifying the CHOSEN
    # recipe's prerequisites against the connected-apps fixture, the same
    # re-verification stance workspace entities get elsewhere in this
    # function (the model's own say-so that something is buildable is never
    # trusted alone).
    #
    # GENERIC (keep for recipe #2+): this loop is entirely data-driven off
    # recipe["prerequisites"] — it needs no per-recipe code.
    # SHAPED BY ONE EXAMPLE: only runs when apps_ws is supplied. None means
    # "no connected-app context" (eval/CLI runs, or the Automations-panel demo
    # before it loads the fixture) — the check is SKIPPED rather than failing
    # every connector rule callers that don't pass one haven't opted into.
    if apps_ws is not None:
        for ai, action in enumerate(spec.get("actions") or []):
            if action.get("type") != "connector":
                continue
            recipe = schema.RECIPES.get(action.get("recipe"))
            if recipe is None:
                continue  # missing/unknown recipe id already flagged above
            unmet = connected_apps.prerequisites_met(apps_ws, recipe["app"],
                                                     recipe["prerequisites"])
            if unmet:
                labels = [connected_apps.PREREQUISITE_LABELS.get(p, p) for p in unmet]
                errors.append(f"action {ai + 1}: '{recipe['name']}' isn't buildable yet — "
                              + "; ".join(labels))

    # ---- {{variable}} references in note bodies must name declared AI variables
    for ni, action in enumerate([] if "ai" in out_of_scope else actions):
        if action.get("type") == "add_note" and action.get("content"):
            for ref in re.findall(r"\{\{\s*([^{}]+?)\s*\}\}", str(action["content"])):
                if ref not in ai_vars:
                    errors.append(f"action {ni + 1}: note references undefined AI "
                                  f"variable '{{{{{ref}}}}}'")

    # hallucinated values are treated as missing: empty the slot, re-ask.
    # When the scrubbed value near-matches a workspace entity (the model often
    # normalized a user typo to the real thing), offer it back as a choice —
    # asking is safe where silently accepting the unproven value wouldn't be.
    #
    # COVERAGE: keyed by (slot, value), never slot alone. Two different problems
    # on ONE slot are two questions — "assign to dara, john, sara" has both an
    # unknown name and an ambiguous one, and slot-level dedup used to drop the
    # second silently (the user asked for three assignees and got two).
    seen = {(m["slot"], _norm(m.get("value"))) for m in missing}
    for h in hallucinated:
        key = (h["slot"], _norm(h["value"]))
        if key in seen:
            continue
        entry = {"slot": h["slot"], "value": h["value"], "question": h["question"]}
        if ws and h.get("entity"):
            kind = h["entity"]
            word = ENTITY_WORD.get(kind, kind)
            # did the USER's own word point here ambiguously? then the honest
            # question is "which one?", not "I couldn't confirm 'John Doe'"
            src, matches = wsmod.ambiguous_source(ws, kind, h["value"],
                                                  conversation_text)
            if src:
                opts = " / ".join(wsmod.label(kind, m) for m in matches)
                entry["question"] = (f"'{src}' matches more than one {word}: "
                                     f"{opts}. Which one?")
                entry["kind"] = "choice"
                entry["options"] = [{"label": wsmod.label(kind, m),
                                     "value": wsmod.canonical(kind, m)}
                                    for m in matches]
            else:
                cands = wsmod.suggest(ws, kind, h["value"])
                if cands:
                    names = [wsmod.canonical(kind, c) for c in cands]
                    if len(names) == 1 and names[0] == h["value"]:
                        # the model normalized a typo to this entity; confirm
                        entry["question"] = (f"Just to confirm — should I use the "
                                             f"{word} '{names[0]}'?")
                    else:
                        entry["question"] = (f"I couldn't confirm '{h['value']}' from "
                                             f"your message — did you mean the {word} "
                                             + " or ".join(f"'{n}'" for n in names) + "?")
                    entry["kind"] = "choice"
                    entry["options"] = [{"label": wsmod.label(kind, c),
                                         "value": wsmod.canonical(kind, c)}
                                        for c in cands]
                    entry["allow_other"] = True
                    entry["other_hint"] = "Something else"
        missing.append(entry)
        seen.add(key)

    # ---- COVERAGE INVARIANT: nothing the user said may leave the turn
    # unaccounted for. Every scrubbed value must be re-asked on its slot or
    # named in a note — silent shrinkage of a slot is a bug class, not an
    # incident. This is the backstop if a path above ever forgets to ask.
    asked_slots = {m["slot"] for m in missing}
    for h in hallucinated:
        if h["slot"] not in asked_slots:
            entity_notes.append(
                f"I set aside '{h['value']}' — I couldn't confirm it from your "
                f"message, so it's not in the rule.")

    # ---- plan questions: trigger, then structural conflicts, then scope, then rest
    def rank(m):
        if m["slot"] == "trigger":
            return 0
        if m["slot"].startswith("conflict:"):
            return 1
        return 2 if m["slot"] == "scope" else 3
    ordered, structured, qseen = [], [], set()
    for m in sorted(missing, key=rank):
        if m["question"] not in qseen:
            ordered.append(m["question"])
            structured.append({
                "slot": m["slot"],
                "prompt": m["question"],
                "kind": m.get("kind", "text"),
                "options": m.get("options", []),
                "multiple": bool(m.get("multiple")),
                "allow_other": bool(m.get("allow_other")) or m.get("kind", "text") == "text",
                "other_hint": m.get("other_hint", ""),
            })
            qseen.add(m["question"])

    # ---- unmappable: requirements the vocabulary genuinely cannot express.
    # Declared, never approximated — the model reaches for this instead of
    # bending "has tag VIP" into `status is VIP`. Like unsupported, it does not
    # block a rule; it states what the rule will NOT do.
    unmappable = [{"request": str(u.get("request") or "").strip(),
                   "why": str(u.get("why") or "").strip()}
                  for u in (spec.get("unmappable") or [])
                  if str(u.get("request") or "").strip()]

    status = ("invalid" if errors else "needs_info" if missing else "complete")
    return {
        "status": status,
        "scope_pinned": scope_pinned,
        "out_of_scope": out_of_scope,
        "assumptions": assumptions,
        "unmappable": unmappable,
        "errors": errors,
        "missing": missing,
        "hallucinated": hallucinated,
        "unsupported": sorted(set(unsupported)),
        "resolutions": resolutions,
        "entity_notes": sorted(set(entity_notes)),
        "questions": ordered[:MAX_QUESTIONS],
        "questions_structured": structured[:MAX_QUESTIONS],
        "questions_pending": max(0, len(ordered) - MAX_QUESTIONS),
    }


def apply_resolutions(spec, result):
    """Rewrite resolved values to their workspace-canonical form ('sarah' ->
    'Sarah Lee') so the draft and final JSON carry real entity names."""
    by_slot = {}
    for r in result.get("resolutions", []):
        by_slot.setdefault(r["slot"], []).append(r)
    for ai, action in enumerate(spec.get("actions") or []):
        for pname in list(action.keys()):
            rs = by_slot.get(f"actions[{ai}].{pname}")
            if not rs:
                continue
            val = action[pname]
            for r in rs:
                if isinstance(val, list):
                    val = [r["canonical"] if _norm(v) == _norm(r["value"]) else v
                           for v in val]
                elif _norm(val) == _norm(r["value"]):
                    val = r["canonical"]
            action[pname] = val
    return spec


def scrub(spec, result):
    """(see below) — also applies the pilot-scope drop."""
    """Remove hallucinated values from the spec so the draft shown to the user
    contains only user-sourced facts. Also applies the scope pin: when the user
    explicitly answered "run it on everything", conditions the model re-derived
    from earlier messages are dropped so the spec matches what was validated."""
    oos = result.get("out_of_scope") or []
    if oos:
        if "ai" in oos:
            spec["ai_extract"] = None
        spec["condition_groups"] = [
            [c for c in g
             if not ("ai" in oos and c.get("property") == "ai_variable")
             and not ("time" in oos and c.get("property") in schema.TIME_PROPERTIES)]
            for g in (spec.get("condition_groups") or [])]
        spec["condition_groups"] = [g for g in spec["condition_groups"] if g]
    if result.get("scope_pinned"):
        spec["condition_groups"] = []
        spec["scope_confirmed"] = True
    bad = {(h["slot"], _norm(h["value"])) for h in result["hallucinated"]}
    if not bad:
        return spec
    for ai, action in enumerate(spec.get("actions") or []):
        for pname in list(action.keys()):
            slot = f"actions[{ai}].{pname}"
            val = action[pname]
            if isinstance(val, list):
                action[pname] = [v for v in val if (slot, _norm(v)) not in bad]
            elif (slot, _norm(val)) in bad:
                action[pname] = None
    for gi, group in enumerate(spec.get("condition_groups") or []):
        for ci, cond in enumerate(group):
            slot = f"condition_groups[{gi}][{ci}].values"
            cond["values"] = [v for v in (cond.get("values") or [])
                              if (slot, _norm(v)) not in bad]
    for vi, var in enumerate((spec.get("ai_extract") or {}).get("variables") or []):
        slot = f"ai_extract.variables[{vi}].options"
        var["options"] = [o for o in (var.get("options") or [])
                          if (slot, _norm(o)) not in bad]
    return spec
