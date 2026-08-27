"""This engine's charter (2026-08-27 cleanup): App Activation only. Every
automation it builds has to touch a real app via a connector action (recipe /
native_action_id / custom_plan) -- Track A (apps/) is app-only by construction
already, so this file is entirely about Track B's boundary: an automation
made up ENTIRELY of generic Hiver moves (tag, assign, status, note, reply,
notify, move inbox), with no app action anywhere in it, is a rule Hiver can
build fine but is out of scope for THIS engine. See copilot.py's own gate
(placed right after the "wholly unmappable" branch it sits beside) for the
reasoning on why this is `errors`/status "invalid", not `unmappable` /a
feature-request offer -- nothing is missing from the catalogue, the ask is
simply the wrong shape for this product surface.

All pure code, no LLM call -- same reasoning as this engine's other capability
test files: router.classify()/automation.extract.extract() are monkeypatched
throughout, so this only proves the CODE-side gate, not a live model's
ability to recognize when an ask has no app content.

Run: python3 test_app_scope.py
"""
import sys

import copilot
import router
from automation import extract as automation_extract

OUT_OF_SCOPE_PHRASE = "only builds automations connected to a real app"


def _classify(track="automation", capability_question=None, no_intent=None):
    def classify(client, messages, model=None):
        return {"intent_summary": "test", "track": track,
                "capability_question": capability_question, "no_intent": no_intent}
    return classify


def _extract(trigger=None, scope_confirmed=False, condition_groups=None, actions=None,
             unmappable=None, closing=False, no_intent=None, capability_question=None):
    def extract(client, messages, model=None, ws=None, on_event=None, app=None):
        return {"intent_summary": "test", "trigger": trigger,
                "scope_confirmed": scope_confirmed,
                "condition_groups": condition_groups or [], "actions": actions or [],
                "ai_extract": None, "unsupported_requests": [], "closing": closing,
                "capability_question": capability_question, "no_intent": no_intent,
                "unmappable": unmappable or [], "enabled_inboxes": None,
                "feature_request_requested": None}
    return extract


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    oc, oae = router.classify, automation_extract.extract

    def turn(msgs, extract_fn, classify_fn=None):
        router.classify = classify_fn or _classify()
        automation_extract.extract = extract_fn
        try:
            return copilot.respond_structured(None, msgs)
        finally:
            router.classify, automation_extract.extract = oc, oae

    # ---- a pure-Hiver ask (no app action anywhere) is out of scope ----------
    tag_only = turn(
        [{"role": "user", "content": "tag emails from acme.com as VIP"}],
        _extract(trigger="new_conversation_inbound", scope_confirmed=True,
                condition_groups=[[{"property": "from_domain", "op": "contains",
                                    "values": ["acme.com"], "variable": None}]],
                actions=[{"type": "tag", "tags": ["VIP"]}]))
    check("a rule made ENTIRELY of generic actions (tag) -> invalid, not complete",
          tag_only["status"] == "invalid")
    check("the error names the app-usecase boundary, not a vague failure",
          any(OUT_OF_SCOPE_PHRASE in e for e in tag_only["errors"]))
    check("no lingering trigger/inbox questions once it's flagged out of scope",
          tag_only["questions_structured"] == [] and tag_only["questions"] == [])

    assign_only = turn(
        [{"role": "user", "content": "assign new conversations to Dana"}],
        _extract(trigger="new_conversation_inbound", scope_confirmed=True,
                actions=[{"type": "assign", "target": "Dana"}]))
    check("a different generic action (assign) is equally out of scope",
          assign_only["status"] == "invalid"
          and any(OUT_OF_SCOPE_PHRASE in e for e in assign_only["errors"]))

    multi_generic = turn(
        [{"role": "user", "content": "tag VIP, assign to Dana, and add a note"}],
        _extract(trigger="new_conversation_inbound", scope_confirmed=True,
                actions=[{"type": "tag", "tags": ["VIP"]}, {"type": "assign", "target": "Dana"},
                         {"type": "add_note", "content": "flagged", "pinned": False}]))
    check("several generic actions together are STILL out of scope -- it only "
          "takes ONE real app action to clear the gate, not just one generic one",
          multi_generic["status"] == "invalid")

    # ---- an app-connected automation is completely unaffected ---------------
    app_only = turn(
        [{"role": "user", "content": "create a clickup task for every new conversation"}],
        _extract(trigger="new_conversation_inbound", scope_confirmed=True,
                actions=[{"type": "connector", "recipe": None,
                         "native_action_id": "clickup_create_task",
                         "target_name": "Support", "title_hint": "Follow up",
                         "test_contact_email": None, "custom_plan": None}]))
    check("an app-connected automation never trips the gate",
          app_only["status"] != "invalid"
          or not any(OUT_OF_SCOPE_PHRASE in e for e in app_only["errors"]))

    # ---- generic actions ALONGSIDE a real app action are exactly the point --
    mixed = turn(
        [{"role": "user", "content": "tag it VIP and also create a clickup task"}],
        _extract(trigger="new_conversation_inbound", scope_confirmed=True,
                actions=[{"type": "tag", "tags": ["VIP"]},
                         {"type": "connector", "recipe": None,
                         "native_action_id": "clickup_create_task",
                         "target_name": "Support", "title_hint": "Follow up",
                         "test_contact_email": None, "custom_plan": None}]))
    check("combining a generic action WITH a real app action is unaffected -- "
          "that's exactly what this engine is for",
          mixed["status"] != "invalid"
          or not any(OUT_OF_SCOPE_PHRASE in e for e in mixed["errors"]))

    # ---- nothing extracted yet -> gate doesn't fire prematurely -------------
    nothing_yet = turn(
        [{"role": "user", "content": "I want to set up an automation"}],
        _extract(trigger=None, scope_confirmed=False, actions=[]))
    check("no actions extracted yet -- the gate waits, doesn't guess ahead of "
          "what the user actually said",
          not any(OUT_OF_SCOPE_PHRASE in e for e in nothing_yet["errors"]))

    # ---- read-only turns are untouched ---------------------------------------
    cap_q = turn(
        [{"role": "user", "content": "what does assignment support?"}],
        _extract(trigger="new_conversation_inbound", scope_confirmed=True,
                actions=[{"type": "tag", "tags": ["VIP"]}],
                capability_question="assignment options"),
        classify_fn=_classify(capability_question="assignment options"))
    check("a capability question riding on top of a pure-generic draft is "
          "READ-ONLY -- the gate never fires on it, same as every other "
          "read-only classification in this engine",
          not any(OUT_OF_SCOPE_PHRASE in e for e in cap_q["errors"]))

    gibberish = turn(
        [{"role": "user", "content": "asdkjfhaskjdf"}],
        _extract(trigger=None, scope_confirmed=False, actions=[], no_intent="gibberish"),
        classify_fn=_classify(no_intent="gibberish"))
    check("gibberish is read-only too -- never flagged out of scope",
          not any(OUT_OF_SCOPE_PHRASE in e for e in gibberish["errors"]))

    # ---- the wholly-unmappable branch (a different gate, sits right next to
    # this one) still wins when NOTHING at all was extracted -- these two
    # gates must not fight each other.
    wholly_unmappable = turn(
        [{"role": "user", "content": "close it when the clickup task closes"}],
        _extract(trigger=None, scope_confirmed=False, actions=[],
                unmappable=[{"request": "trigger off the ClickUp task closing",
                            "why": "external app state changes aren't triggers here"}]))
    check("wholly-unmappable (zero actions extracted) is a DIFFERENT gate -- "
          "this one never fires when actions is empty",
          not any(OUT_OF_SCOPE_PHRASE in e for e in wholly_unmappable["errors"]))
    check("the wholly-unmappable branch's own behavior is untouched by this "
          "gate existing beside it",
          wholly_unmappable["unmappable"]
          and any(q["slot"] == "feature_request_offer"
                  for q in wholly_unmappable["questions_structured"]))

    print(f"app scope unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
