"""Grader for the automation wire schema (trigger/condition_groups/actions):
canonicalize rules from either vocabulary (raw prod schema or engine output
schema) into one comparison form, then diff. Originally built for the
general real-world eval set; App Activation (2026-08-27) narrowed this
engine's scope to app-connected automations only, so connector-eval-set.jsonl
is this grader's primary user now — the underlying wire schema (and so the
canonicalize/diff logic) is unchanged either way, a connector automation is
still a trigger/conditions/actions rule, just with a connector action in it.

Tiers:
  1. validity  — did the engine emit parseable rule JSON at all (handled in report.py)
  2. this file — deterministic canonical structural diff, per-slot scores
  3. judge     — only for Tier-2 mismatches flagged as possibly-equivalent (report.py emits the list)

Condition semantics (assumed, pending engineering confirmation):
  condition_groups are AND'd together; conditions within a group are OR'd;
  a condition's `values` array is itself an any-of list.

Self-test:  python3 grader.py --self-test
  Every ideal_output diffed against itself must be a perfect match.
"""
import json
import re
import sys
from pathlib import Path

EVAL_SET = Path(__file__).parent / "connector-eval-set.jsonl"

# ---------------------------------------------------------------- vocab maps
# Left side: any alias an engine (v1 golden-set vocab, or future v2 schema) may emit.
# Right side: canonical token (prod dump vocabulary, lowercased).
# TODO(v2-schema): finalize once the v2 spec enums are frozen; every enum the
# schema defines must appear here (or already be canonical) — that check IS the
# schema-coverage validation.

TRIGGER_MAP = {
    # v1 engine emits its knowledge-base's human-readable names:
    "new conversation (inbound or outbound) created": "new_conversation",
    "new conversation (inbound) received": "new_conversation_inbound",
    "new conversation (inbound) created": "new_conversation_inbound",
    "new conversation (outbound) created": "new_conversation_outbound",
    "new conversation (outbound) sent": "new_conversation_outbound",
    "external reply received (from anyone)": "new_email_incoming_from_anyone",
    "external reply received (from contact)": "new_email_incoming_from_contact",
    "reply sent from mailbox": "new_email_outgoing",
    "new_conversation_created": "new_conversation",
    "external_reply_received_anyone": "new_email_incoming_from_anyone",
    "external_reply_received_contact": "new_email_incoming_from_contact",
    "mailbox_reply_sent": "new_email_outgoing",
    # canonical names pass through:
    "new_conversation": "new_conversation",
    "new_conversation_inbound": "new_conversation_inbound",
    "new_conversation_outbound": "new_conversation_outbound",
    "new_email_incoming_from_anyone": "new_email_incoming_from_anyone",
    "new_email_incoming_from_contact": "new_email_incoming_from_contact",
    "new_email_outgoing": "new_email_outgoing",
    "conversation_moved_to_inbox": "conversation_moved_to_inbox",
}

FIELD_MAP = {
    "from email": "from",
    "to email": "to",
    "cc email": "cc",
    "bcc email": "bcc",
    "from domain": "from_domain",
    "to domain": "to_domain",
    "reply-to": "reply_to",
    "reply-to email": "reply_to",
    "email subject": "subject",
    "email body": "body",
    "sender": "from",
    "sender_email": "from",
    "from_address": "from",
    "recipient": "to",
    "sender_domain": "from_domain",
    "email_body": "body",
    "subject_line": "subject",
    # TODO(v2-schema): add v2 field enums here when defined.
}

OP_MAP = {
    # values arrays are any-of by definition, so list-flavored ops fold into the base op
    "contains any of": "contains",
    "contains any": "contains",
    "contains one of": "contains",
    "is any of": "is",
    "is_any_of": "is",
    "any_of": "is",
    "one_of": "is",
    "is exactly": "is",
    "does not contain any of": "does not contain",
    "equals": "is",
    "equal": "is",
    "exact": "is",
    "is_exactly": "is",
    "not_contains": "does not contain",
    "does_not_contain": "does not contain",
    "is_not": "is not",
    "not_equals": "is not",
    "regex": "matches",
    "matches_regex": "matches",
    "none_of": "is_none_of",
    "not_exists": "does_not_exist",
    # TODO(v2-schema): confirm v2 operator enums.
}

ACTION_TYPE_MAP = {
    "add tag": "add_tag",
    "add tags": "add_tag",
    "remove tag": "remove_tag",
    "remove tags": "remove_tag",
    "assign to": "assign",
    "assign to user": "assign",
    "update status": "status",
    "add note": "add_note",
    "send email notification": "send_notification",
    "round-robin assign": "assign_among",
    "assign among": "assign_among",
    "tag": "add_tag",
    "apply_tag": "add_tag",
    "untag": "remove_tag",
    "assign_to": "assign",
    "round_robin_assign": "assign_among",
    "round_robin": "assign_among",
    "set_status": "status",
    "change_status": "status",
    "close": "status",  # value defaults handled in _canon_action
    "note": "add_note",
    "internal_note": "add_note",
    "send_email": "send_mail",
    "auto_reply": "send_mail",
    "send_reply": "send_mail",
    "reply": "send_mail",
    "notify": "send_notification",
    "notification": "send_notification",
    "move_to_inbox": "add_to_sm",
    "add_to_inbox": "add_to_sm",
    "remove_from_inbox": "remove_from_sm",
    "custom_field": "set_custom_field",
    "approval": "create_approval_request",
}

STATUS_MAP = {"closed": "close", "opened": "open", "snoozed": "pending"}


# ------------------------------------------------------------- normalization
def _norm(s):
    """Whitespace/case normalization for comparison values."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _norm_values(values):
    return tuple(sorted(_norm(v) for v in (values or []) if _norm(v) != ""))


def _norm_time_slot(ts):
    if not ts:
        return None
    start, end = ts.get("start"), ts.get("end")
    tz = ts.get("timezone")
    if start is None and end is None and tz is None:
        return None
    # timezone strings look like "-240 America/New_York"; keep the IANA part
    tz_name = str(tz).split()[-1] if tz else None
    return (start, end, tz_name)


# ------------------------------------------------------ shape detection/conv
def _flat_to_groups(rule):
    """Convert v1-golden flat shape {conditions:[{field,operator,value}], logic}
    into prod-style condition_groups (AND of OR-groups)."""
    conds = []
    for c in rule.get("conditions") or []:
        vals = c.get("values")
        if vals is None:
            vals = [c.get("value")] if c.get("value") is not None else []
        conds.append({
            "property": c.get("field") or c.get("property"),
            "op": c.get("operator") or c.get("op"),
            "values": vals,
        })
    logic = (rule.get("logic") or "").upper()
    if not conds:
        return []
    if logic == "OR":
        return [conds]              # one group, OR'd within
    return [[c] for c in conds]     # AND: each condition its own group


# ------------------------------------------------------------- canonicalize
def _canon_condition(c):
    prop = _norm(c.get("property"))
    prop = FIELD_MAP.get(prop, prop)
    op = _norm(c.get("op"))
    op = OP_MAP.get(op, op)
    values = _norm_values(c.get("values"))

    # AI variables compare NAME-AGNOSTICALLY: the admin's variable name is an
    # arbitrary identifier no engine can guess ("is_hts_coo_dimensions_related"),
    # so ai_variable conditions compare on the referenced variable's type (+options),
    # its op, and its values. API variables keep name comparison (names are external).
    var = c.get("ai_variable") or c.get("variable")
    if var and prop == "ai_variable":
        if isinstance(var, dict):
            vtype = _norm(var.get("type") or var.get("variable_type"))
            vopts = tuple(sorted(_norm(o) for o in (var.get("options") or [])))
        else:
            vtype, vopts = "", ()
        prop = f"ai_variable:{vtype}"
        if vopts:
            prop += f":{list(vopts)}"
    elif var and prop == "http_api_variable":
        name = var.get("name") if isinstance(var, dict) else var
        prop = f"{prop}:{_norm(name)}"

    extras = []
    ts = _norm_time_slot(c.get("time_slot"))
    if ts:
        extras.append(f"time_slot={ts}")
    opts = sorted(_norm(o) for o in (c.get("options") or []))
    if opts:
        extras.append(f"options={opts}")
    return (prop, op, values, tuple(extras))


def _aval(a, *keys):
    """First non-empty value among the given keys plus common target aliases."""
    for k in (*keys, "target or value", "target", "value", "values"):
        if a.get(k) not in (None, ""):
            return a[k]
    return None


def _canon_action(a):
    t = _norm(a.get("type"))
    t = ACTION_TYPE_MAP.get(t, t)
    if t.startswith("custom_field:"):  # prod dump encodes field name in the type
        field = t.split(":", 1)[1]
        val = _norm((a.get("detail") or {}).get("cf_value", a.get("value")))
        return [("set_custom_field", field, val)]
    if t.startswith("connector"):
        return [("connector", t)]
    if t == "add_tag" or t == "remove_tag":
        tags = a.get("tags")
        if not tags:
            v = _aval(a)
            tags = v if isinstance(v, list) else ([v] if v else [])
        return [(t, _norm(tag)) for tag in tags]
    if t == "assign":
        v = _norm(_aval(a, "user"))
        return [("assign", v)]
    if t == "unassign":
        return [("assign", "unassign")]
    if t == "assign_among":
        targets = a.get("targets") or a.get("users")
        if not targets:
            v = _aval(a)
            targets = v if isinstance(v, list) else ([v] if v else [])
        return [("assign_among", tuple(sorted(_norm(x) for x in targets)))]
    if t == "status":
        v = _norm(a.get("status") or _aval(a))
        return [("status", STATUS_MAP.get(v, v))]
    if t == "add_note":
        content = a.get("content") or a.get("text") or _aval(a) or ""
        pinned = bool(a.get("pinned") or a.get("pin_note"))
        refs = re.findall(r"\{\{\s*[^{}]+?\s*\}\}", str(content))
        if refs:
            # Note bodies that embed {{variables}} are model-authored templates
            # (prose + placeholders); the deterministic gradeable part is the
            # template shape, not the wording — same treatment as send_mail bodies.
            return [("add_note_template", len(refs), pinned)]
        return [("add_note", _norm(content), pinned)]
    if t == "send_notification":
        detail = a.get("detail") or {}
        email_on = bool(detail.get("isSendMailEnabled", a.get("email", False)))
        return [("send_notification", email_on)]
    if t == "send_mail":
        return [("send_mail",)]  # template bodies not present in the dump
    if t == "set_custom_field":
        return [("set_custom_field", _norm(a.get("field")), _norm(a.get("value")))]
    if t in ("add_to_sm", "remove_from_sm"):
        detail = a.get("detail") or {}
        ids = (detail.get("selected_sm_ids") or []) + (detail.get("extra_sm_ids") or [])
        if detail.get("sm_id"):
            ids.append(detail["sm_id"])
        ids += a.get("inboxes") or []
        return [(t, tuple(sorted(_norm(x) for x in ids)))]
    if t in ("add_followers", "create_approval_request"):
        return [(t,)]
    return [(t,)]  # unknown action type: compare on type alone


def _canon_ai_extract(ai):
    """Name-agnostic: variables compare as a multiset of (type, options).
    Names are arbitrary identifiers and descriptions are model-authored prose;
    neither is deterministically gradeable (see eval/README)."""
    if not ai:
        return None
    out = []
    for v in ai.get("variables", []):
        out.append((
            _norm(v.get("type") or v.get("variable_type")),
            tuple(sorted(_norm(o) for o in (v.get("options") or []))),
        ))
    return tuple(sorted(out)) or None


def canonicalize(rule):
    """Accepts a rule in prod-dump shape (condition_groups) or v1-flat shape
    (conditions + logic). Returns the canonical comparison form."""
    if rule is None:
        return None
    trig = _norm(rule.get("trigger"))
    trig = TRIGGER_MAP.get(trig, trig)

    if "condition_groups" in rule:
        groups_src = rule["condition_groups"] or []
    else:
        groups_src = _flat_to_groups(rule)

    groups = []
    for g in groups_src:
        conds = [_canon_condition(c) for c in g]
        # Within a group conditions are OR'd and values are any-of, so
        # (p,op,[a]) OR (p,op,[b]) == (p,op,[a,b]) — merge them.
        merged = {}
        for prop, op, values, extras in conds:
            key = (prop, op, extras)
            merged.setdefault(key, set()).update(values)
        canon_g = tuple(sorted((p, o, tuple(sorted(v)), e)
                               for (p, o, e), v in merged.items()))
        if canon_g:
            groups.append(canon_g)
    groups = tuple(sorted(groups))

    actions = []
    for a in rule.get("actions") or []:
        actions.extend(_canon_action(a))
    actions = tuple(sorted(str(x) for x in actions))

    return {
        "trigger": trig,
        "groups": groups,
        "actions": actions,
        "ai_extract": _canon_ai_extract(rule.get("ai_extract")),
    }


# --------------------------------------------------------------------- diff
def _set_diff(expected, got):
    e, g = list(expected), list(got)
    matched = []
    for item in list(e):
        if item in g:
            matched.append(item)
            g.remove(item)
            e.remove(item)
    n_match, n_exp, n_got = len(matched), len(expected), len(got)
    precision = n_match / n_got if n_got else (1.0 if n_exp == 0 else 0.0)
    recall = n_match / n_exp if n_exp else 1.0
    return {
        "matched": n_match,
        "missing": [str(x) for x in e],
        "hallucinated": [str(x) for x in g],
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }


def diff(expected_canon, got_canon):
    """Compare two canonical rules. Returns per-slot verdicts + strict_pass."""
    if got_canon is None:
        return {"strict_pass": False, "error": "no_rule"}
    trig_ok = expected_canon["trigger"] == got_canon["trigger"]
    cond = _set_diff(expected_canon["groups"], got_canon["groups"])
    act = _set_diff(expected_canon["actions"], got_canon["actions"])
    ai_exp, ai_got = expected_canon["ai_extract"], got_canon["ai_extract"]
    if ai_exp is None and ai_got is None:
        ai = None
    else:
        ai = _set_diff(ai_exp or (), ai_got or ())
    strict = (
        trig_ok
        and not cond["missing"] and not cond["hallucinated"]
        and not act["missing"] and not act["hallucinated"]
        and (ai is None or (not ai["missing"] and not ai["hallucinated"]))
    )
    return {
        "trigger": {"expected": expected_canon["trigger"],
                    "got": got_canon["trigger"], "match": trig_ok},
        "conditions": cond,
        "actions": act,
        "ai_extract": ai,
        "strict_pass": strict,
    }


# ---------------------------------------------------------------- self-test
def self_test():
    records = [json.loads(l) for l in open(EVAL_SET)]
    fails = 0
    for r in records:
        c = canonicalize(r["ideal_output"])
        d = diff(c, c)
        if not d["strict_pass"]:
            fails += 1
            print(f"SELF-TEST FAIL {r['id']}: {json.dumps(d, indent=1)[:400]}")

    # flat-shape conversion check: v1-golden style rule must match its prod twin
    flat = {"trigger": "new_conversation_created",
            "conditions": [{"field": "SUBJECT", "operator": "equals", "value": "Refund"},
                           {"field": "body", "operator": "contains", "value": "refund"}],
            "logic": "OR",
            "actions": [{"type": "tag", "value": "Billing"},
                        {"type": "assign_to", "target": "Ryan"}]}
    prod = {"trigger": "new_conversation",
            "condition_groups": [[{"property": "subject", "op": "is", "values": ["refund"]},
                                  {"property": "body", "op": "contains", "values": ["Refund"]}]],
            "ai_extract": None,
            "actions": [{"type": "assign", "target": "Ryan"},
                        {"type": "add_tag", "tags": ["billing"]}]}
    d = diff(canonicalize(prod), canonicalize(flat))
    if not d["strict_pass"]:
        fails += 1
        print("SELF-TEST FAIL flat-shape conversion:", json.dumps(d, indent=1))

    # negative check: a genuinely different rule must NOT pass
    wrong = dict(prod, actions=[{"type": "assign", "target": "Someone Else"}])
    if diff(canonicalize(prod), canonicalize(wrong))["strict_pass"]:
        fails += 1
        print("SELF-TEST FAIL: differing rules scored as identical")

    total = len(records) + 2
    print(f"self-test: {total - fails}/{total} passed"
          + ("" if fails == 0 else f"  ({fails} FAILED)"))
    return fails == 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    print(__doc__)
