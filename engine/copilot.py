"""v2 turn loop: extract -> validate -> ask or finalize.

Reply contract (what the user sees each turn):
  needs_info -> the closest legal draft with what's-known filled in, missing slots
                marked, and up to 3 planned questions
  complete   -> the final legal structure (prose WHEN/IF/THEN + machine JSON)
  invalid    -> honest statement of what couldn't be mapped
Unsupported asks are always named, never silently dropped or faked.
"""
import json

import docent
import executor
import extract
import features
import schema
import validator

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
    prop = schema.PROPERTY_LABELS.get(c["property"], c["property"])
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
        recipe = schema.RECIPES.get(a.get("recipe"))
        name = recipe["name"] if recipe else need(a.get("recipe"))
        return f"run connector recipe — {name}, test-run with {need(a.get('test_contact_email'))}"
    return t


def render_structure(spec):
    lines = []
    trig = spec.get("trigger")
    # builder vocabulary, not internal ids — users verify in the language they know
    lines.append("WHEN  " + (schema.TRIGGER_LABELS.get(trig, trig)
                             if trig in schema.TRIGGERS else MISSING))
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
            actions.append({"type": "connector", "recipe": a.get("recipe"),
                            "test_contact_email": a.get("test_contact_email")})
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
    """Does any rule value appear in the given message? Then that message added
    content and cannot be a closing — the code gate behind extraction rule 13,
    which the model alone gets wrong ('use the Urgent tag, thanks!' -> mt-014)."""
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


def connector_test_run(spec):
    """If the (complete) spec contains a connector action, fire its recipe's
    chain for real via executor.py using the test_contact_email the admin
    supplied, and return the result. This is the connector analogue of the
    draft -> final step every other action type already goes through: those
    have no external side effect to verify before being marked done, so they
    need no such check; a connector rule calls a real service, so it does.
    Returns None when the spec has no connector action (the common case)."""
    for a in spec.get("actions") or []:
        if a.get("type") == "connector" and a.get("recipe") and a.get("test_contact_email"):
            return executor.test_run(a["recipe"], a["test_contact_email"])
    return None


def feature_request_result(spec, apps_ws):
    """Track A: resolve an app_feature ask (extract.py rule 20) through
    features.py, NOT validator.py — validator only understands the
    automation rule shape (trigger/conditions/actions), and a Track A ask
    has none of those by design. Returns None when this turn isn't Track A."""
    fid = spec.get("app_feature")
    if not fid:
        return None
    if apps_ws is None:
        return {"status": "invalid", "feature_id": fid,
                "errors": ["no connected-app context available"]}
    result = features.enable_feature(fid, apps_ws)
    result["feature_id"] = fid
    return result


def _empty_result(feature_result):
    """A validator.validate()-shaped stand-in for the Track A path, so
    respond()/respond_structured() can read result["status"]/["errors"] the
    same way regardless of which track the turn took."""
    return {
        "status": feature_result["status"], "scope_pinned": False, "out_of_scope": [],
        "assumptions": [], "unmappable": [], "errors": feature_result.get("errors", []),
        "missing": [], "hallucinated": [], "unsupported": [], "resolutions": [],
        "entity_notes": [], "questions": [], "questions_structured": [],
        "questions_pending": 0, "feature_request": feature_result,
    }


def render_feature(spec, feature_result):
    """Track A's analogue of render_structure(): Track A has no trigger,
    conditions, or actions to render — just the one feature this turn
    resolved and whether it's usable yet."""
    fid = feature_result.get("feature_id") or spec.get("app_feature")
    f = schema.FEATURES.get(fid, {})
    name = f.get("name", fid or MISSING)
    lines = [f"APP FEATURE  {name}"]
    if f.get("description"):
        lines.append(f.get("description"))
    if feature_result["status"] == "complete":
        lines.append("STATUS  Enabled")
    else:
        lines.append("STATUS  Can't enable yet — "
                     + "; ".join(feature_result.get("errors", [])))
    return "\n".join(lines)


def _turn(client, messages, model, ws, apps_ws=None, on_event=None):
    """Shared per-turn pipeline: extract -> validate -> scrub -> resolve.
    Track A (app_feature set) branches BEFORE the automation validator —
    see feature_request_result()."""
    user_msgs = [m["content"] for m in messages if m["role"] == "user"]
    convo_text = "\n".join(user_msgs)
    spec = extract.extract(client, messages, model, ws=ws, on_event=on_event)
    if on_event:
        on_event({"stage": "validating"})
    feature_result = feature_request_result(spec, apps_ws)
    if feature_result is not None:
        result = _empty_result(feature_result)
    else:
        result = validator.validate(spec, convo_text, ws=ws, user_messages=user_msgs,
                                    apps_ws=apps_ws)
        spec = validator.scrub(spec, result)
        spec = validator.apply_resolutions(spec, result)
        result["feature_request"] = None
    last_user = next((m["content"] for m in reversed(messages)
                      if m["role"] == "user"), "")
    if spec.get("closing") and _contributed(spec, last_user):
        spec["closing"] = False
    # capability questions: the model only classifies; the answer is composed
    # in code from schema.py so nothing unbuildable is ever taught. A question
    # is never a closing.
    if spec.get("capability_question"):
        spec["closing"] = False
    # gibberish/off-topic: read-only, like a capability question — a
    # meaningless message must never mutate a draft the user built
    if spec.get("no_intent"):
        spec["closing"] = False
    return spec, result


def respond_structured(client, messages, model=extract.MODEL, ws=None, apps_ws=None,
                       on_event=None):
    """One turn, machine-readable: everything a UI needs to render the state.
    Same pipeline as respond(); returns a dict instead of prose."""
    spec, result = _turn(client, messages, model, ws, apps_ws=apps_ws, on_event=on_event)
    complete = result["status"] == "complete"
    feature_result = result.get("feature_request")
    return {
        "status": result["status"],
        "track": "feature" if feature_result is not None else "automation",
        "feature_request": feature_result,
        "test_run": connector_test_run(spec) if complete and feature_result is None else None,
        "capability_answer": (docent.answer(spec["capability_question"])
                              if spec.get("capability_question") else None),
        "no_intent": spec.get("no_intent") or None,
        "closing": bool(spec.get("closing")),
        "done": bool(spec.get("closing")) and complete,
        "intent_summary": spec.get("intent_summary") or "",
        "spec": spec,
        "rule": to_final_json(spec) if complete and feature_result is None else None,
        "draft": render_feature(spec, feature_result) if feature_result is not None
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
    if test_run["status"] == "ok":
        return f"Test run: assigned to {test_run['final']['target']}."
    if test_run["status"] == "no_match":
        return f"Test run: nothing was assigned — {test_run['reason']}."
    return f"Test run: couldn't complete — {test_run.get('reason', 'unknown error')}."


def respond(client, messages, model=extract.MODEL, ws=None, apps_ws=None):
    """One turn. messages = full chat history [{role, content}]. Returns reply text.
    With a workspace, extraction may use lookup tools and the validator re-verifies
    every resolution against the user's own words."""
    spec, result = _turn(client, messages, model, ws, apps_ws=apps_ws)

    feature_result = result.get("feature_request")
    if feature_result is not None:
        # Track A: a completely different shape from an automation turn —
        # no WHEN/IF/THEN, no questions loop, no closing/draft logic below,
        # all of which assume a rule with a trigger.
        if feature_result["status"] == "complete":
            feat = feature_result["feature"]
            return (f"{feat['name']} is set up — {feat['description']}\n\n"
                    + render_feature(spec, feature_result))
        return (render_feature(spec, feature_result)
               + "\n\nThis isn't buildable yet in this workspace.")

    is_followup = any(m["role"] == "assistant" for m in messages)
    last_user = (messages[-1]["content"].lower() if messages else "")
    wants_draft = any(k in last_user for k in ("show me", "what do you have", "so far", "the draft"))
    # full draft: first turn, after a scrubbed hallucination (transparency), or on request
    show_full = (not is_followup) or bool(result["hallucinated"]) or wants_draft

    closing = bool(spec.get("closing"))

    parts = []
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
