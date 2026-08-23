"""Outer turn loop: router -> (automation | app_setup) extraction -> resolve
-> render. Reply contract (what the user sees each turn):
  needs_info -> the closest legal draft with what's-known filled in, missing slots
                marked, and up to 3 planned questions (automation) or 1 (app_setup)
  complete   -> the final legal structure (prose + machine JSON, or "enabled")
  invalid    -> honest statement of what couldn't be mapped
Unsupported asks are always named, never silently dropped or faked.

router.classify() decides FIRST which track a turn is in; only THEN does the
matching package's own extractor/resolver run — automation/ (trigger,
conditions, actions, connector recipes) and apps/ (Track A feature setup)
are genuine peers that don't know about each other. This file is the only
place that talks to both.
"""
import json

import docent
import mailbox_lookup
import router
from apps import extract as apps_extract
from apps import schema as apps_schema
from apps import setup as apps_setup
from automation import executor as automation_executor
from automation import extract as automation_extract
from automation import plan_validator as automation_plan_validator
from automation import schema as automation_schema
from automation import validator as automation_validator

MISSING = "⟨required — not provided yet⟩"

SHORT_TRIGGER = {
    "new_conversation_inbound": "new inbound conversation",
    "new_conversation_outbound": "new outbound conversation",
    "new_conversation": "any new conversation",
    "new_email_incoming_from_anyone": "incoming reply (anyone)",
    "new_email_incoming_from_contact": "reply from contact",
    "new_email_outgoing": "outgoing email",
    "conversation_moved_to_inbox": "moved into inbox",
}


def _render_condition(c):
    if c.get("property") == "ai_variable":
        name = c.get("variable") or "⟨which variable?⟩"
        if c.get("op") in ("exists", "does_not_exist"):
            return f"AI:{name} {c['op']}"
        vals = ", ".join(f"'{v}'" for v in c.get("values", [])) or MISSING
        return f"AI:{name} {c['op']} {vals}"
    vals = ", ".join(f"'{v}'" for v in c.get("values", [])) or MISSING
    prop = automation_schema.PROPERTY_LABELS.get(c["property"], c["property"])
    return f"{prop} {c['op']} {vals}"


def _render_ai_variable(v):
    line = f"{v.get('name') or MISSING} ({v.get('type') or '?'})"
    if v.get("options"):
        line += " one of: " + ", ".join(v["options"])
    if v.get("description"):
        line += f" — \"{v['description']}\""
    return line


def _render_action(a):
    t = a["type"]
    def need(v):
        if isinstance(v, list):
            return ", ".join(f"'{x}'" for x in v) if v else MISSING
        return f"'{v}'" if v not in (None, "") else MISSING
    if t in ("add_tag", "remove_tag"):
        return f"{'add' if t == 'add_tag' else 'remove'} tag {need(a.get('tags'))}"
    if t == "assign":
        return f"assign to {need(a.get('target'))}"
    if t == "assign_among":
        how = {"round_robin": "round robin",
               "load_balancing": "load balancing"}.get(a.get("distribution"))
        return (f"assign among {need(a.get('targets'))} by "
                + (how if how else MISSING + " ← round robin or load balancing?"))
    if t == "status":
        return f"set status to {need(a.get('status_value'))}"
    if t == "add_note":
        note = f"add note {need(a.get('content'))}"
        return note + (" (pinned)" if a.get("pinned") else "")
    if t == "send_mail":
        return f"send reply — {need(a.get('body_hint'))}"
    if t == "send_notification":
        return "notify" + (" (email + in-app)" if a.get("email_enabled") else " (in-app)")
    if t == "add_to_sm":
        return f"add to shared inbox {need(a.get('inbox'))}"
    if t == "remove_from_sm":
        return "remove from this shared inbox"
    if t == "connector":
        native = automation_schema.NATIVE_ACTIONS.get(a.get("native_action_id"))
        if native:
            return (f"run native action — {native['name']}, "
                    f"target {need(a.get('target_name'))}, titled {need(a.get('title_hint'))}")
        recipe = automation_schema.RECIPES.get(a.get("recipe"))
        plan = a.get("custom_plan")
        if recipe:
            name, chain = recipe["name"], recipe.get("chain", [])
        elif plan:
            name = f"dynamically-composed plan — {plan.get('plan_summary') or 'unnamed'}"
            chain = automation_plan_validator.to_chain(plan)["chain"]
        else:
            name, chain = need(a.get("recipe")), []
        line = f"run connector recipe — {name}, test-run with {need(a.get('test_contact_email'))}"
        terminal = _connector_terminal(chain)
        if terminal:
            verb = ("assign the conversation to" if terminal["kind"] == "assign"
                    else "tag the conversation with")
            line += f" → then {verb} {terminal['value']} (extracted from Salesforce)"
        return line
    return t


def _connector_terminal(chain):
    """A connector's own terminal chain step (assign or add_tag), read
    generically off the chain itself — not hardcoded to one recipe's
    variable name, and works identically for a fixed RECIPES chain or a
    dynamically-composed plan's chain (plan_validator.to_chain) — so the
    THEN line and the exported JSON both show what the connector actually
    does end to end (look up data, then act on it), not just that it ran.
    None for a chain with no terminal step (schema.py's own
    SHAPED-BY-ONE-EXAMPLE note already flags that as unbuilt for RECIPES)."""
    for step in chain:
        if step.get("kind") == "assign":
            return {"kind": "assign", "value": step.get("target")}
        if step.get("kind") == "add_tag":
            return {"kind": "add_tag", "value": ", ".join(step.get("tags") or [])}
    return None


def render_structure(spec):
    lines = []
    trig = spec.get("trigger")
    # builder vocabulary, not internal ids — users verify in the language they know
    lines.append("WHEN  " + (automation_schema.TRIGGER_LABELS.get(trig, trig)
                             if trig in automation_schema.TRIGGERS else MISSING))
    ai_vars = (spec.get("ai_extract") or {}).get("variables") or []
    if ai_vars:
        lines.append("AI    extract per conversation:\n      " + "\n      ".join(
            f"{i}. {_render_ai_variable(v)}" for i, v in enumerate(ai_vars, 1)))
    groups = spec.get("condition_groups") or []
    if groups:
        parts = ["(" + "  OR  ".join(_render_condition(c) for c in g) + ")" for g in groups]
        lines.append("IF    " + "\n  AND ".join(parts))
    elif spec.get("scope_confirmed"):
        lines.append("IF    (no conditions — runs on every matching conversation, as you specified)")
    else:
        lines.append("IF    (no conditions — assumed to run on every matching "
                     "conversation; say if it should only match a subset)")
    acts = spec.get("actions") or []
    if acts:
        lines.append("THEN  " + "\n      ".join(
            f"{i}. {_render_action(a)}" for i, a in enumerate(acts, 1)))
    else:
        lines.append("THEN  " + MISSING)
    return "\n".join(lines)


def render_compact(spec):
    """One-line state strip for follow-up turns: enough orientation to not scroll up,
    without re-rendering the whole draft."""
    trig = SHORT_TRIGGER.get(spec.get("trigger"), "⟨when?⟩")
    groups = spec.get("condition_groups") or []
    if groups:
        conds = " AND ".join(
            ("(" + " OR ".join(_render_condition(c) for c in g) + ")") if len(g) > 1
            else _render_condition(g[0]) for g in groups)
    elif spec.get("scope_confirmed"):
        conds = "everything"
    else:
        conds = "⟨scope?⟩"
    acts = " + ".join(_render_action(a) for a in spec.get("actions") or []) or "⟨actions?⟩"
    return f"So far: WHEN {trig} · IF {conds} · THEN {acts}".replace(MISSING, "⟨?⟩")


def to_final_json(spec):
    """Grader/prod-compatible shape."""
    actions = []
    for a in spec.get("actions") or []:
        t = a["type"]
        if t in ("add_tag", "remove_tag"):
            actions.append({"type": t, "tags": a.get("tags") or []})
        elif t == "assign":
            actions.append({"type": "assign", "target": a.get("target")})
        elif t == "assign_among":
            actions.append({"type": "assign_among", "targets": a.get("targets") or [],
                            "distribution": a.get("distribution")})
        elif t == "status":
            actions.append({"type": "status", "status": a.get("status_value")})
        elif t == "add_note":
            actions.append({"type": "add_note", "content": a.get("content"),
                            "pinned": bool(a.get("pinned"))})
        elif t == "send_mail":
            actions.append({"type": "send_mail"})
        elif t == "send_notification":
            actions.append({"type": "send_notification",
                            "detail": {"isSendMailEnabled": bool(a.get("email_enabled"))}})
        elif t in ("add_to_sm", "remove_from_sm"):
            actions.append({"type": t, "inboxes": [a["inbox"]] if a.get("inbox") else []})
        elif t == "connector":
            native = automation_schema.NATIVE_ACTIONS.get(a.get("native_action_id"))
            recipe = automation_schema.RECIPES.get(a.get("recipe"))
            plan = a.get("custom_plan")
            chain = (recipe.get("chain", []) if recipe
                    else automation_plan_validator.to_chain(plan)["chain"] if plan else [])
            terminal = _connector_terminal(chain)
            actions.append({
                "type": "connector", "recipe": a.get("recipe"),
                "native_action_id": a.get("native_action_id"),
                "target_name": a.get("target_name") if native else None,
                "title_hint": a.get("title_hint") if native else None,
                "custom_plan": plan,
                "test_contact_email": a.get("test_contact_email"),
                "assigns_to": terminal["value"] if terminal and terminal["kind"] == "assign" else None,
                "tags_with": terminal["value"] if terminal and terminal["kind"] == "add_tag" else None,
            })
    ai_vars = (spec.get("ai_extract") or {}).get("variables") or []
    var_by_name = {v["name"]: v for v in ai_vars if v.get("name")}

    def cond_json(c):
        out = {"property": c["property"], "op": c["op"], "values": c.get("values", [])}
        if c["property"] == "ai_variable" and c.get("variable"):
            v = var_by_name.get(c["variable"], {})
            out["ai_variable"] = {"name": c["variable"], "type": v.get("type"),
                                  "options": v.get("options") or []}
        return out

    ai_extract = None
    if ai_vars:
        ai_extract = {"variables": [{"name": v.get("name"), "type": v.get("type"),
                                     "description": v.get("description", ""),
                                     "options": v.get("options") or []}
                                    for v in ai_vars]}
    return {"trigger": spec.get("trigger"),
            "condition_groups": [[cond_json(c) for c in g]
                                 for g in spec.get("condition_groups") or []],
            "ai_extract": ai_extract,
            "actions": actions}


def _workspace_lines(result):
    parts = []
    seen, disclose = set(), []
    for r in result.get("resolutions", []):
        if _norm_key(r["value"]) == _norm_key(r["canonical"]):
            continue  # pure casing fixes don't need a callout
        line = f"'{r['value']}' → {r.get('detail') or r['canonical']}"
        if line not in seen:
            seen.add(line)
            disclose.append(line)
    if disclose:
        parts.append("Matched to your workspace: " + "; ".join(disclose) +
                     ". Say if I got one wrong.")
    if result.get("entity_notes"):
        parts.append("Heads up: " + " ".join(result["entity_notes"]))
    return parts


def _norm_key(s):
    return " ".join(str(s or "").split()).lower()


def _contributed(spec, last_text):
    """Does any AUTOMATION rule value appear in the given message? Then that
    message added content and cannot be a closing — the code gate behind
    extraction rule 13, which the model alone gets wrong ('use the Urgent
    tag, thanks!' -> mt-014)."""
    norm = " ".join(str(last_text).split()).lower()
    vals = []
    for g in spec.get("condition_groups") or []:
        for c in g:
            vals += c.get("values") or []
    for a in spec.get("actions") or []:
        for k in ("tags", "targets"):
            vals += a.get(k) or []
        for k in ("target", "inbox", "status_value", "content", "body_hint"):
            if a.get(k):
                vals.append(a[k])
    return any(str(v).strip() and " ".join(str(v).split()).lower() in norm
               for v in vals)


def _contributed_app_setup(spec, last_text):
    """The apps/ (Track A) analogue of _contributed(): did the given message
    name a record, field, or inbox that's now in the accumulated setup?
    connect_requested isn't checked here, same as _contributed() never
    checks booleans like `pinned` — there's no literal value to match
    against the message text."""
    norm = " ".join(str(last_text).split()).lower()
    vals = []
    for k in ("objects", "account_fields", "contact_fields", "inboxes"):
        vals += spec.get(k) or []
    return any(str(v).strip() and " ".join(str(v).split()).lower() in norm
               for v in vals)


def connector_test_run(spec):
    """If the (complete) automation spec contains a connector action, fire
    it for real via automation/executor.py and return the result — the
    connector analogue of the draft -> final step every other action type
    already goes through: those have no external side effect to verify
    before being marked done, so they need no such check; a connector rule
    calls a real service, so it does. Returns None when the spec has no
    connector action (the common case).

    Three mechanisms, three executor entry points: a native action
    (run_native_action) needs no test_contact_email at all — there's no
    per-contact CRM lookup to prove, just its own target_name/title_hint,
    already required before this spec could reach "complete". A recipe
    (test_run) or custom_plan (test_run_plan) both need test_contact_email;
    a custom_plan action only ever reaches "complete" after validator.py
    has already proven this exact test run succeeds, so that case is a
    re-run for display, not the first time it's been tried."""
    for a in spec.get("actions") or []:
        if a.get("type") != "connector":
            continue
        if a.get("native_action_id"):
            return automation_executor.run_native_action(a["native_action_id"], a)
        if not a.get("test_contact_email"):
            continue
        if a.get("recipe"):
            return automation_executor.test_run(a["recipe"], a["test_contact_email"])
        if a.get("custom_plan"):
            return automation_executor.test_run_plan(a["custom_plan"], a["test_contact_email"])
    return None


def feature_request_result(app_spec, apps_ws, ws=None):
    """Track A: resolve an app_setup turn through apps.setup.resolve_setup()
    — a genuine peer of automation_validator.validate(), not a branch off
    of it. `app_spec` (from apps/extract.py) IS the feature_setup shape
    resolve_setup() expects (connect_requested/objects/account_fields/
    contact_fields/inboxes), plus `feature` naming which one. `ws` is the
    entity workspace fixture (for the shared-inbox enable step) — same
    fixture the automation track already threads through for entity
    resolution. Returns None when app_spec has no feature match at all (an
    app_setup-routed turn that still couldn't match any FEATURES entry —
    see apps/extract.py rule 8)."""
    fid = app_spec.get("feature")
    if not fid:
        return None
    if apps_ws is None:
        return {"status": "invalid", "feature_id": fid, "progress": {},
                "errors": ["no connected-app context available"],
                "questions": [], "questions_structured": []}
    result = apps_setup.resolve_setup(fid, app_spec, apps_ws, ws)
    result["feature_id"] = fid
    return result


def _empty_result(feature_result):
    """A validate()-shaped stand-in for the Track A path, so
    respond()/respond_structured() can read result["status"]/["questions"]/
    etc. the same way regardless of which track the turn took."""
    return {
        "status": feature_result["status"], "scope_pinned": False, "out_of_scope": [],
        "assumptions": [], "unmappable": [], "errors": feature_result.get("errors", []),
        "missing": [], "hallucinated": [], "unsupported": [], "resolutions": [],
        "entity_notes": [], "questions": feature_result.get("questions", []),
        "questions_structured": feature_result.get("questions_structured", []),
        "questions_pending": 0, "feature_request": feature_result,
    }


def render_feature(feature_result):
    """apps/'s analogue of render_structure(): Track A has no trigger,
    conditions, or actions to render — just this feature's setup progress
    (connected? which objects/fields chosen so far?) and whether it's fully
    enabled yet, the same "show what's known, mark what's open" spirit as
    render_structure()'s ⟨holes⟩."""
    from apps import schema as apps_schema
    fid = feature_result.get("feature_id")
    f = apps_schema.FEATURES.get(fid, {})
    name = f.get("name", fid or MISSING)
    lines = [f"APP FEATURE  {name}"]
    if f.get("description"):
        lines.append(f.get("description"))
    progress = feature_result.get("progress") or {}
    if "connected" in progress:
        lines.append("CONNECTED  " + ("yes" if progress["connected"] else MISSING))
    if progress.get("objects"):
        lines.append("RECORDS  " + ", ".join(progress["objects"]))
    for obj, fields in (progress.get("fields_by_object") or {}).items():
        lines.append(f"  {obj} FIELDS  " + ", ".join(fields))
    if progress.get("inboxes"):
        lines.append("ENABLED FOR  " + ", ".join(progress["inboxes"]))
    if feature_result["status"] == "complete":
        lines.append("STATUS  Enabled")
    elif feature_result["status"] == "invalid":
        lines.append("STATUS  Can't enable — " + "; ".join(feature_result.get("errors", [])))
    else:
        lines.append("STATUS  In progress")
    preview = feature_result.get("preview")
    if preview:
        lines.append(_render_feature_preview(preview))
    return "\n".join(lines)


def _render_feature_preview(preview):
    """"Test on a real conversation" (capability 7) for a Track A view
    feature — the real field values apps.setup.preview_feature() actually
    found for one real contact, rendered the same "show what's real" way
    _render_test_run() shows a connector's test-run result."""
    if preview["status"] == "no_match":
        return f"TEST RUN  no match — {preview['reason']}"
    lines = [f"TEST RUN  against {preview['contact_email']}:"]
    for obj, values in (preview.get("values_by_object") or {}).items():
        rendered = ", ".join(f"{k}: {v if v is not None else MISSING}"
                             for k, v in values.items())
        lines.append(f"  {obj}  {rendered}")
    return "\n".join(lines)


def _is_write_feature(feature_result):
    """True when this completed Track A feature creates a NEW record
    (kind="write", e.g. salesforce_create_contact) rather than showing
    existing data. Used to withhold the "test on a real conversation" nudge
    for write features — apps/setup.py already refuses to compute a preview
    for them (there's no existing data to show), so offering the SAME
    "try a real conversation" text a view feature gets would promise
    something the engine has no way to follow through on: a live test found
    this exact gap — the nudge appeared, but replying "yes, test it" (or
    naming any real contact) just re-rendered the same completion message,
    since nothing downstream was ever wired to act on it for a write
    feature. Never invite an action there is no code path for."""
    fid = (feature_result or {}).get("feature_id")
    return apps_schema.FEATURES.get(fid, {}).get("kind") == "write"


def _test_conversation_suggestions(limit=2):
    """A few real conversations to nudge toward trying, once a capability
    is complete but hasn't been test-run yet — the same
    mailbox_lookup.testable_conversations() the connector's own
    test_contact_email question already offers as choices, phrased as a
    suggestion here since a Track A test-run is a courtesy, never required
    for completeness the way it is for a dynamically-composed connector
    plan."""
    convos = mailbox_lookup.testable_conversations(limit=limit)
    if not convos:
        return ""
    examples = "; ".join(f"'{c['from']}' ({c['subject']})" for c in convos)
    return f"Want to see it in action? Try a real conversation, e.g. {examples}."


def _mapping_explanation(spec, feature_result):
    """The requested conversational step this codebase didn't have yet:
    identify the usecase, map it to the catalog, and SAY the mapping out
    loud before diving into setup questions — "you want X, I can do that
    via Y, here's how" — rather than jumping straight to "which records
    should this show?" with no explanation of why. Composed ENTIRELY from
    the matched capability's own name/description (never invented), the
    same "answer only from schema.py" discipline docent.py's capability
    answers already follow — this only differs from those in WHEN it
    fires (once, unprompted, on the turn a capability is first identified)
    rather than in response to an explicit "what can you do" question.

    Only ONE turn ever gets this line — see _turn()'s is_first_turn gate —
    so a multi-turn setup conversation doesn't re-explain itself on every
    answer. SHAPED BY ONE EXAMPLE: gated on "first turn of the whole
    conversation" because that's when a usecase is normally first stated;
    a capability that only becomes identifiable on turn 2+ (the user was
    vague at first) won't get this sentence — the existing intent_summary
    framing still covers "here's what I understood" for that case, just
    without the explicit "and here's the capability that solves it" tie-in.
    Returns None when nothing has been matched yet (nothing to explain)."""
    if feature_result is not None:
        f = apps_schema.FEATURES.get(feature_result.get("feature_id"))
        if f is None:
            return None
        return (f"This looks like a fit for **{f['name']}** (an existing Salesforce "
                f"app capability) — {f['description']} Let's get it set up.")
    for a in spec.get("actions") or []:
        if a.get("type") != "connector":
            continue
        if a.get("native_action_id"):
            n = automation_schema.NATIVE_ACTIONS.get(a["native_action_id"])
            if n:
                return (f"This looks like a fit for **{n['name']}** (a native "
                        f"{n['app'].title()} action, not an API call this engine "
                        f"composes) — {n['description']} Let's get it set up.")
        if a.get("recipe"):
            r = automation_schema.RECIPES.get(a["recipe"])
            if r:
                return (f"This looks like a fit for **{r['name']}** (a ready-made "
                        f"automation recipe) — {r['description']} Let's get it set up.")
        if a.get("custom_plan"):
            summary = a["custom_plan"].get("plan_summary")
            return ("This looks like it needs a composed Salesforce lookup, since "
                    "there's no ready-made action for it" + (f" — {summary}" if summary else "")
                    + ". Let's get it set up.")
    return None


def _turn(client, messages, model, ws, apps_ws=None, on_event=None):
    """Shared per-turn pipeline: router decides the track, then that track's
    OWN extract -> resolve pipeline runs. Returns (spec, result) where
    result["feature_request"] is set (non-None) for an app_setup turn and
    None for an automation turn — respond()/respond_structured() branch on
    that, unchanged from before this file's tracks were split into
    packages."""
    if on_event:
        on_event({"stage": "routing"})
    route = router.classify(client, messages, model)
    last_user = next((m["content"] for m in reversed(messages)
                      if m["role"] == "user"), "")
    # the mapping explanation (see _mapping_explanation) only ever fires on
    # the conversation's first turn — an assistant message already in
    # history means a capability was either already explained or is still
    # being narrowed down, either way not worth re-explaining.
    is_first_turn = not any(m["role"] == "assistant" for m in messages)

    if route["track"] == "app_setup":
        if on_event:
            on_event({"stage": "extracting", "track": "app_setup"})
        spec = apps_extract.extract(client, messages, model)
        spec["capability_question"] = route.get("capability_question")
        spec["no_intent"] = route.get("no_intent")
        feature_result = feature_request_result(spec, apps_ws, ws)
        result = _empty_result(feature_result) if feature_result is not None else {
            "status": "needs_info", "scope_pinned": False, "out_of_scope": [],
            "assumptions": [], "unmappable": spec.get("unmappable") or [], "errors": [],
            "missing": [], "hallucinated": [], "unsupported": [], "resolutions": [],
            "entity_notes": [], "questions": [], "questions_structured": [],
            "questions_pending": 0, "feature_request": None,
        }
        if spec.get("closing") and _contributed_app_setup(spec, last_user):
            spec["closing"] = False
        if feature_result is None:
            # No Track A feature actually matched this app_setup-track turn
            # (a bare capability question, a gibberish message, or an
            # app-setup-sounding ask with no catalog match) — apps_extract's
            # spec has NO trigger/actions/condition_groups at all (see
            # apps/extract.py's RESPONSE_SCHEMA), so respond_structured()
            # below would report "track": "automation" (since feature_result
            # is None) while handing the UI a spec missing the very fields
            # RuleCard assumes exist, crashing on `spec.actions.length`. This
            # is exactly the "one track's shape leaking into the other's
            # consumer" bug apps/ and automation/ were split to prevent —
            # normalize to the SAME empty shape a fresh automation turn
            # already has, preserving only the read-only classifications and
            # honest unmappable/closing signals.
            spec = {
                "intent_summary": spec.get("intent_summary", ""),
                "trigger": None, "scope_confirmed": False, "condition_groups": [],
                "actions": [], "ai_extract": None, "unsupported_requests": [],
                "closing": spec.get("closing", False),
                "unmappable": spec.get("unmappable") or [],
                "capability_question": spec.get("capability_question"),
                "no_intent": spec.get("no_intent"),
            }
    else:
        if on_event:
            on_event({"stage": "extracting", "track": "automation"})
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        convo_text = "\n".join(user_msgs)
        spec = automation_extract.extract(client, messages, model, ws=ws, on_event=on_event)
        spec["capability_question"] = route.get("capability_question")
        spec["no_intent"] = route.get("no_intent")
        if on_event:
            on_event({"stage": "validating"})
        result = automation_validator.validate(spec, convo_text, ws=ws, user_messages=user_msgs,
                                               apps_ws=apps_ws)
        spec = automation_validator.scrub(spec, result)
        spec = automation_validator.apply_resolutions(spec, result)
        result["feature_request"] = None
        if spec.get("closing") and _contributed(spec, last_user):
            spec["closing"] = False

    spec["mapping_explanation"] = (
        _mapping_explanation(spec, result.get("feature_request")) if is_first_turn else None)

    # capability questions: the model only classifies (router.py); the answer
    # is composed in code from schema.py so nothing unbuildable is ever
    # taught. A question is never a closing.
    if spec.get("capability_question"):
        spec["closing"] = False
    # gibberish/off-topic: read-only, like a capability question — a
    # meaningless message must never mutate a draft the user built
    if spec.get("no_intent"):
        spec["closing"] = False
    return spec, result


def respond_structured(client, messages, model=None, ws=None, apps_ws=None,
                       on_event=None):
    """One turn, machine-readable: everything a UI needs to render the state.
    Same pipeline as respond(); returns a dict instead of prose."""
    spec, result = _turn(client, messages, model or automation_extract.MODEL, ws,
                        apps_ws=apps_ws, on_event=on_event)
    complete = result["status"] == "complete"
    feature_result = result.get("feature_request")
    # capability 7 for Track A: a courtesy nudge once the feature is fully
    # enabled but nobody's named a contact to preview it against yet — the
    # SAME text respond() has always shown; without this field a structured
    # (UI) consumer had no way to surface it, even though the mailbox/fixture
    # data backing it was there the whole time (a real gap, not a design
    # choice: capability 7 was wired into respond()'s prose but never into
    # this dict, so the browser UI could never show it).
    feature_test_suggestion = (
        _test_conversation_suggestions()
        if (feature_result is not None and feature_result["status"] == "complete"
            and not feature_result.get("preview")
            and not _is_write_feature(feature_result))
        else None
    )
    return {
        "status": result["status"],
        "track": "feature" if feature_result is not None else "automation",
        "feature_request": feature_result,
        "feature_test_suggestion": feature_test_suggestion,
        "test_run": connector_test_run(spec) if complete and feature_result is None else None,
        "capability_answer": (docent.answer(spec["capability_question"])
                              if spec.get("capability_question") else None),
        "no_intent": spec.get("no_intent") or None,
        "mapping_explanation": spec.get("mapping_explanation"),
        "closing": bool(spec.get("closing")),
        "done": bool(spec.get("closing")) and complete,
        "intent_summary": spec.get("intent_summary") or "",
        "spec": spec,
        "rule": to_final_json(spec) if complete and feature_result is None else None,
        "draft": render_feature(feature_result) if feature_result is not None
                 else render_structure(spec),
        "assumptions": result.get("assumptions", []),
        "unmappable": result.get("unmappable", []),
        "questions": result["questions"],
        "questions_structured": result.get("questions_structured", []),
        "questions_pending": result["questions_pending"],
        "errors": result["errors"],
        "unsupported": result["unsupported"],
        "hallucinated": [h["value"] for h in result["hallucinated"]],
        "resolutions": result.get("resolutions", []),
        "entity_notes": result.get("entity_notes", []),
    }


def _render_test_run(test_run):
    if test_run is None:
        return None
    if "result" in test_run:
        # native-action shape (executor.run_native_action) — no "final" key,
        # no "no_match" outcome: it either ran or it didn't.
        if test_run["status"] == "ok":
            url = (test_run.get("result") or {}).get("url")
            return f"Test run: done — {url}." if url else "Test run: done."
        return f"Test run: couldn't complete — {test_run.get('reason', 'unknown error')}."
    # recipe/custom_plan shape (executor.run_chain) — terminal is assign OR
    # add_tag (see automation/executor.py's run_chain "final" kinds), so this
    # reads whichever one actually ran instead of assuming assign.
    if test_run["status"] == "ok":
        final = test_run.get("final") or {}
        if final.get("type") == "add_tag":
            return f"Test run: tagged with {', '.join(final.get('tags') or [])}."
        return f"Test run: assigned to {final.get('target')}."
    if test_run["status"] == "no_match":
        return f"Test run: nothing was assigned — {test_run['reason']}."
    return f"Test run: couldn't complete — {test_run.get('reason', 'unknown error')}."


def respond(client, messages, model=None, ws=None, apps_ws=None):
    """One turn. messages = full chat history [{role, content}]. Returns reply text.
    With a workspace, extraction may use lookup tools and the validator re-verifies
    every resolution against the user's own words."""
    spec, result = _turn(client, messages, model or automation_extract.MODEL, ws,
                        apps_ws=apps_ws)

    feature_result = result.get("feature_request")
    # the mapping explanation (see _mapping_explanation) — the "identify the
    # usecase, map it to the catalog, and SAY so before diving into setup
    # questions" step — leads whichever branch below actually runs, Track A
    # or B alike, since both are equally "a capability was just matched."
    mapping = spec.get("mapping_explanation")
    if feature_result is not None:
        # Track A: a completely different shape from an automation turn —
        # no WHEN/IF/THEN, no closing logic below (all of which assume a
        # rule with a trigger) — but it DOES have its own one-question-at-a-
        # time loop (apps.setup.resolve_setup), rendered the same "closest
        # known state, then what's next" way as the automation path.
        if feature_result["status"] == "complete":
            feat = feature_result["feature"]
            lead = f"{mapping}\n\n" if mapping else ""
            tail = ("" if feature_result.get("preview") or _is_write_feature(feature_result)
                   else "\n\n" + _test_conversation_suggestions())
            return (lead + f"{feat['name']} is set up — {feat['description']}\n\n"
                    + render_feature(feature_result) + tail).rstrip()
        parts = ([mapping] if mapping else []) + [render_feature(feature_result)]
        if feature_result["status"] == "invalid":
            parts.append("This isn't usable yet in this workspace: "
                         + "; ".join(feature_result.get("errors", [])) + ".")
            return "\n\n".join(parts)
        if feature_result.get("errors"):
            parts.append("Couldn't use that: " + "; ".join(feature_result["errors"]) + ".")
        qs = feature_result.get("questions") or []
        if qs:
            parts.append(f"To finish setting this up: {qs[0]}")
        return "\n\n".join(parts)

    is_followup = any(m["role"] == "assistant" for m in messages)
    last_user = (messages[-1]["content"].lower() if messages else "")
    wants_draft = any(k in last_user for k in ("show me", "what do you have", "so far", "the draft"))
    # full draft: first turn, after a scrubbed hallucination (transparency), or on request
    show_full = (not is_followup) or bool(result["hallucinated"]) or wants_draft

    closing = bool(spec.get("closing"))

    parts = [mapping] if mapping else []
    if spec.get("no_intent"):
        parts.append(
            "I couldn't find an automation in that. Tell me what should happen "
            "and when — for example \"tag emails from acme.com as VIP\" or "
            "\"assign new incoming email to Dana\".")
        if is_followup:
            parts.append("Your draft is unchanged.")
        return "\n\n".join(parts)
    if spec.get("capability_question"):
        # answer first, from the schema; the rule state follows unchanged
        parts.append(docent.answer(spec["capability_question"]))
    if result["status"] == "complete":
        test_run_line = _render_test_run(connector_test_run(spec))
        if closing and is_followup:
            # the user wrapped up — acknowledge and stop, don't repeat the pitch
            parts.append("All set — the rule is final as shown in the panel. "
                         "Build it in Hiver, and start a new chat for the next one.")
            if test_run_line:
                parts.append(test_run_line)
            parts.append("```json\n"
                         + json.dumps(to_final_json(spec), ensure_ascii=False, indent=1)
                         + "\n```")
            return "\n\n".join(parts)
        parts.append("Here's the automation:")
        parts.append(render_structure(spec))
        parts.extend(_workspace_lines(result))
        if result.get("assumptions"):
            parts.append("Assumed: it " + "; ".join(
                a["summary"] for a in result["assumptions"])
                + " — say if it should only match a subset.")
        if result["unsupported"]:
            parts.append("Not included (not supported yet): " + "; ".join(result["unsupported"]) + ".")
        if result.get("unmappable"):
            parts.append("Couldn't build into the rule: " + "; ".join(
                f"{u['request']} ({u['why']})" for u in result["unmappable"]) + ".")
        if test_run_line:
            parts.append(test_run_line)
        parts.append("```json\n" + json.dumps(to_final_json(spec), ensure_ascii=False, indent=1)
                     + "\n```")
        parts.append("Want any adjustments?")
        return "\n\n".join(parts)

    if show_full:
        if result["hallucinated"] and is_followup:
            dropped = ", ".join(f"'{h['value']}'" for h in result["hallucinated"])
            parts.append(f"I set aside {dropped} — you haven't mentioned it, so I won't "
                         "use it without your say-so. Here's where the rule stands:")
        else:
            if spec.get("intent_summary"):
                parts.append(f"Understood so far: {spec['intent_summary']}")
            parts.append("Closest supported structure, with what you've given me filled in:")
        parts.append(render_structure(spec))
    else:
        parts.append("✓ Got it.")
        parts.append(render_compact(spec))

    parts.extend(_workspace_lines(result))
    if result["errors"]:
        parts.append("Couldn't map: " + "; ".join(result["errors"]) + ".")
    if result["unsupported"]:
        parts.append("Heads up — not supported yet: " + "; ".join(result["unsupported"]) + ".")
    if result.get("unmappable"):
        parts.append("Couldn't build into the rule: " + "; ".join(
            f"{u['request']} ({u['why']})" for u in result["unmappable"]) + ".")

    qs = result["questions"]
    if closing and qs:
        parts.append("Sounds like that's everything from your side — but the rule "
                     "can't run yet without a bit more:")
    if len(qs) == 1:
        parts.append(f"To finish it: {qs[0]}")
    elif qs:
        block = "To finish it I need:\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1))
        block += "\n(One message is fine — e.g. \"1: refund; 2: Sarah\".)"
        if result["questions_pending"]:
            block += f"\n(+{result['questions_pending']} more after these.)"
        parts.append(block)
    parts.append("```json\nnull\n```")
    return "\n\n".join(parts)
