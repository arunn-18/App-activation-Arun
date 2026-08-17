"""Preview dry-run: replay a draft rule over one week of (fixture) mail.

The point is blast radius BEFORE the rule exists: "would have matched 37 of 209
conversations last week" turns an abstract scope into a number the user can
sanity-check — the everything-assumption especially ("all 209" is either exactly
what they meant, or instantly, visibly wrong).

Pure code over the FINAL rule JSON (grader/prod shape from copilot.to_final_json):
the same determinism argument as the validator — the model never gets to guess
what a rule matches. Anything code cannot evaluate (AI variables, time-window
and staleness conditions, the moved-to-inbox trigger) makes the preview
UNAVAILABLE with a stated reason, never silently approximate.

Prototype reads mailbox.json; production would run the same shapes against
Hiver's conversation search API.
"""
import json
import re
from datetime import datetime
from pathlib import Path

MAILBOX_PATH = Path(__file__).parent / "mailbox.json"

SAMPLE_N = 3
NOT_PREVIEWABLE_PROPS = {"email_creation_time", "date", "hours_passed_since",
                         "ai_variable"}


def load_mailbox(path=MAILBOX_PATH):
    return json.loads(Path(path).read_text())["emails"]


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _domain(addr):
    addr = _norm(addr)
    return addr.split("@", 1)[1] if "@" in addr else addr


def _trigger_match(email, trigger):
    inbound = email["direction"] == "inbound"
    new = email["new_conversation"]
    if trigger == "new_conversation_inbound":
        return inbound and new
    if trigger == "new_conversation_outbound":
        return not inbound and new
    if trigger == "new_conversation":
        return new
    if trigger == "new_email_incoming_from_anyone":
        return inbound and not new
    if trigger == "new_email_incoming_from_contact":
        return inbound and not new and not _domain(email["from"]).endswith(
            "brightpath.example")
    if trigger == "new_email_outgoing":
        return not inbound
    return None  # conversation_moved_to_inbox etc.: not represented in mail data


def _field(email, prop):
    """The email text(s) a condition property inspects. Lists stay lists —
    address headers hold several addresses and 'contains' means any of them."""
    if prop == "from":
        return [email["from"]]
    if prop in ("to", "cc", "bcc"):
        return list(email.get(prop) or [])
    if prop == "reply_to":
        return [email.get("reply_to") or ""]
    if prop == "from_domain":
        return [_domain(email["from"])]
    if prop == "to_domain":
        return [_domain(a) for a in email.get("to") or []]
    if prop == "reply_to_domain":
        return [_domain(email.get("reply_to") or "")]
    if prop in ("subject", "body"):
        return [email.get(prop) or ""]
    if prop == "status":
        return [email.get("status") or ""]
    if prop == "day":
        return [datetime.fromisoformat(email["received_at"]).strftime("%A")]
    return None


def _op_match(op, haystacks, values):
    hs = [_norm(h) for h in haystacks]
    vs = [_norm(v) for v in values if _norm(v)]
    if not vs:
        return False
    if op == "contains":
        return any(v in h for v in vs for h in hs)
    if op in ("is", "is_any_of"):
        return any(v == h for v in vs for h in hs)
    if op == "does not contain":
        return not any(v in h for v in vs for h in hs)
    if op == "is not":
        return not any(v == h for v in vs for h in hs)
    if op == "matches":
        for v in vs:
            try:
                if any(re.search(v, h) for h in hs):
                    return True
            except re.error:
                if any(v in h for h in hs):
                    return True
        return False
    return None


def _cond_match(email, cond):
    prop = cond.get("property")
    if prop in NOT_PREVIEWABLE_PROPS:
        return None
    haystacks = _field(email, prop)
    if haystacks is None:
        return None
    return _op_match(cond.get("op"), haystacks, cond.get("values") or [])


def preview(rule, emails=None):
    """rule: final JSON (trigger, condition_groups, actions). Returns
    {previewable, reason?, window_days, total, matched, sample[]}."""
    emails = emails if emails is not None else load_mailbox()
    trigger = rule.get("trigger")

    for g in rule.get("condition_groups") or []:
        for c in g:
            if c.get("property") in NOT_PREVIEWABLE_PROPS:
                return {"previewable": False,
                        "reason": f"conditions on '{c['property']}' can't be "
                                  "dry-run over past mail"}
    if trigger == "conversation_moved_to_inbox":
        return {"previewable": False,
                "reason": "moved-to-inbox events aren't in the mail history"}

    known = {"new_conversation_inbound", "new_conversation_outbound",
             "new_conversation", "new_email_incoming_from_anyone",
             "new_email_incoming_from_contact", "new_email_outgoing"}
    if trigger not in known:
        return {"previewable": False, "reason": f"trigger '{trigger}' can't be "
                                                "dry-run over past mail"}
    pool = [e for e in emails if _trigger_match(e, trigger)]

    matched = []
    for e in pool:
        ok = True
        for g in rule.get("condition_groups") or []:      # groups AND'd
            r = [_cond_match(e, c) for c in g]            # conditions OR'd
            if None in r:
                return {"previewable": False,
                        "reason": "a condition in this rule can't be dry-run"}
            if not any(r):
                ok = False
                break
        if ok:
            matched.append(e)

    times = [e["received_at"] for e in emails]
    window = (datetime.fromisoformat(max(times))
              - datetime.fromisoformat(min(times))).days + 1
    return {
        "previewable": True,
        "window_days": window,
        "total": len(pool),
        "matched": len(matched),
        "sample": [{"from": e["from"], "subject": e["subject"],
                    "received_at": e["received_at"]}
                   for e in matched[:SAMPLE_N]],
    }
