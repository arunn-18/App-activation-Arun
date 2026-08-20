"""Track A tests: a real multi-turn setup flow (Authentication -> pick
records -> pick fields per record, from a mocked "describe" call -> enable
for the shared inbox(es) it applies to), per the 2026-08-18 product spec
("Apps Activation Steps: Usecase-wise steps"). Pure code, no LLM call,
except where noted.

This file replaced an earlier, much smaller version that only checked a
single yes/no prerequisite gate — a real live run showed that shape was
wrong: Track A needs the SAME guided-setup mechanics real product use cases
require (pick objects, pick fields from a live API call, pick which
inbox(es) to enable for). See features.resolve_setup()'s module docstring
for the full step order.

The enable step asks WHICH shared inbox(es) this should apply to instead of
a plain yes/no CTA — naming inbox(es) is itself the enable action. It reads
the same demo workspace fixture (workspace.py's shared_inboxes) the
automation track already uses for entity resolution, defaulting to it when
a caller doesn't pass one (see resolve_setup()'s own docstring).

router.classify() and apps.extract.extract() are monkeypatched in the
multi-turn section to isolate copilot.py's ACCUMULATION logic (does the
flat setup spec correctly flow into features.resolve_setup() turn over
turn?) from the LLM's own reliability at choosing a track and filling
those slots from free-form English, which is a separate,
not-yet-verifiable-here concern (see test_connector.py's module docstring
for the same caveat on Track B).

Run: python3 test_track_a.py
"""
import sys

import connected_apps
import copilot
import router
import workspace as wsmod
from apps import extract
from apps import schema
from apps import setup as features

FEATURE_ID = "salesforce_account_contact_details"


def _disconnected_ws():
    return connected_apps.load()  # ships disconnected by default


def _connected_ws():
    ws = connected_apps.load()
    entry = ws["connected_apps"]["salesforce"]
    entry["connected"] = True
    for p in entry["prerequisites"]:
        entry["prerequisites"][p] = True
    return ws


def _setup(**kwargs):
    base = {"connect_requested": None, "objects": None,
            "account_fields": None, "contact_fields": None, "inboxes": None}
    base.update(kwargs)
    return base


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    # ---- step 1: authentication ----------------------------------------------
    disconnected = _disconnected_ws()
    r = features.resolve_setup(FEATURE_ID, _setup(), disconnected)
    check("fresh start, disconnected -> needs_info", r["status"] == "needs_info")
    check("asks to connect, not a generic error",
          r["questions_structured"] and r["questions_structured"][0]["slot"]
          == "feature_setup.connect")
    check("connect question offers the real CTA",
          r["questions_structured"][0]["options"] == [{"label": "Connect Salesforce",
                                                        "value": "connect salesforce"}])
    check("progress reports not connected yet", r["progress"]["connected"] is False)

    r2 = features.resolve_setup(FEATURE_ID, _setup(connect_requested=True), disconnected)
    check("connect_requested flips the SAME apps_ws in place",
          connected_apps.is_connected(disconnected, "salesforce"))
    check("after connecting, moves past auth to the next step",
          r2["status"] == "needs_info"
          and r2["questions_structured"][0]["slot"] == "feature_setup.objects")

    # ---- step 2: record-level visibility (objects) ---------------------------
    connected = _connected_ws()
    r3 = features.resolve_setup(FEATURE_ID, _setup(), connected)
    check("connected, no objects yet -> asks which records",
          r3["status"] == "needs_info"
          and r3["questions_structured"][0]["slot"] == "feature_setup.objects")
    check("object choices are exactly this feature's own list",
          {o["value"] for o in r3["questions_structured"][0]["options"]} == {"Account", "Contact"})

    r4 = features.resolve_setup(FEATURE_ID, _setup(objects=["Opportunity"]), connected)
    check("an object outside this feature's choices is rejected, not silently accepted",
          r4["status"] == "needs_info" and r4["errors"])

    # ---- step 3: field config - read (per object, from the mock describe call)
    r5 = features.resolve_setup(FEATURE_ID, _setup(objects=["Account"]), connected)
    check("objects chosen, no fields yet -> asks Account fields",
          r5["status"] == "needs_info"
          and r5["questions_structured"][0]["slot"] == "feature_setup.account_fields")
    offered = {o["value"] for o in r5["questions_structured"][0]["options"]}
    check("field options include BOTH standard and custom fields (a real describe call)",
          {"Account Name", "Renewal Date"} <= offered)

    r6 = features.resolve_setup(
        FEATURE_ID, _setup(objects=["Account", "Contact"], account_fields=["Account Name"]),
        connected)
    check("Account done, Contact not yet -> asks Contact fields next (in order)",
          r6["status"] == "needs_info"
          and r6["questions_structured"][0]["slot"] == "feature_setup.contact_fields")

    # ---- step 4: enable -- which shared inbox(es), not a plain yes/no CTA -----
    demo_ws = wsmod.load()
    real_inboxes = {i["name"] for i in demo_ws["shared_inboxes"]}

    r7 = features.resolve_setup(
        FEATURE_ID,
        _setup(objects=["Account"], account_fields=["Account Name", "Account Owner"]),
        connected)
    check("all fields chosen, no inboxes yet -> asks which inbox(es) to enable for",
          r7["status"] == "needs_info"
          and r7["questions_structured"][0]["slot"] == "feature_setup.inboxes")
    check("inbox options are the real workspace shared inboxes, not invented",
          {o["value"] for o in r7["questions_structured"][0]["options"]} == real_inboxes)

    r7b = features.resolve_setup(
        FEATURE_ID,
        _setup(objects=["Account"], account_fields=["Account Name", "Account Owner"],
               inboxes=["Not A Real Inbox"]),
        connected)
    check("an inbox not in the workspace is rejected, not silently accepted",
          r7b["status"] == "needs_info" and r7b["errors"])

    r8 = features.resolve_setup(
        FEATURE_ID,
        _setup(objects=["Account"], account_fields=["Account Name", "Account Owner"],
               inboxes=["Support", "Billing"]),
        connected)
    check("inbox(es) named -> complete (naming them IS the enable action)",
          r8["status"] == "complete")
    check("enabled feature carries the actual chosen objects/fields/inboxes",
          r8["feature"]["objects"] == ["Account"]
          and r8["feature"]["fields_by_object"]["Account"] == ["Account Name", "Account Owner"]
          and r8["feature"]["inboxes"] == ["Support", "Billing"])

    # ---- edge cases -----------------------------------------------------------
    unknown = features.resolve_setup("not_a_real_feature", _setup(), connected)
    check("unknown feature id is an error, not a silent no-op / KeyError",
          unknown["status"] == "invalid")

    none_ctx = copilot.feature_request_result({"feature": FEATURE_ID, **_setup()}, None)
    check("no apps_ws context -> invalid, not a crash", none_ctx["status"] == "invalid")

    # ---- copilot._turn / respond_structured: routing + turn-over-turn --------
    # accumulation, exercised through the real pipeline (router.classify and
    # apps.extract.extract are both stubbed) -- the actual regression the
    # earlier bug was about.
    original_classify = router.classify
    original_extract = extract.extract
    convo_ws = _disconnected_ws()

    def fake_classify(client, messages, model=None):
        return {"intent_summary": "test", "track": "app_setup",
                "capability_question": None, "no_intent": None}

    def fake_extract(client, messages, model=None):
        text = " ".join(m["content"] for m in messages if m["role"] == "user").lower()
        setup = _setup()
        if "connect" in text:
            setup["connect_requested"] = True
        if "show account and contact" in text:
            setup["objects"] = ["Account", "Contact"]
        if "account name" in text:
            setup["account_fields"] = ["Account Name", "Account Owner"]
        if "contact email" in text:
            setup["contact_fields"] = ["Contact Email"]
        if "support inbox" in text:
            setup["inboxes"] = ["Support"]
        return {"intent_summary": "test", "feature": FEATURE_ID, "closing": False,
                "unmappable": [], **setup}

    router.classify = fake_classify
    extract.extract = fake_extract
    try:
        msgs = [{"role": "user", "content": "set up salesforce account cards"}]
        s1 = copilot.respond_structured(None, msgs, apps_ws=convo_ws)
        check("turn 1: routes to feature track", s1["track"] == "feature")
        check("turn 1: asks to connect (nothing else is possible yet)",
              s1["feature_request"]["questions_structured"][0]["slot"]
              == "feature_setup.connect")

        msgs.append({"role": "assistant", "content": s1["draft"]})
        msgs.append({"role": "user", "content": "yes, connect salesforce"})
        s2 = copilot.respond_structured(None, msgs, apps_ws=convo_ws)
        check("turn 2: connecting persists -- moved on to picking records",
              s2["feature_request"]["questions_structured"][0]["slot"]
              == "feature_setup.objects")

        msgs.append({"role": "assistant", "content": s2["draft"]})
        msgs.append({"role": "user", "content": "show account and contact"})
        s3 = copilot.respond_structured(None, msgs, apps_ws=convo_ws)
        check("turn 3: asks fields for the first object",
              s3["feature_request"]["questions_structured"][0]["slot"]
              == "feature_setup.account_fields")

        msgs.append({"role": "assistant", "content": s3["draft"]})
        msgs.append({"role": "user", "content": "account name and account owner"})
        s4 = copilot.respond_structured(None, msgs, apps_ws=convo_ws)
        check("turn 4: moves to the second object's fields",
              s4["feature_request"]["questions_structured"][0]["slot"]
              == "feature_setup.contact_fields")

        msgs.append({"role": "assistant", "content": s4["draft"]})
        msgs.append({"role": "user", "content": "contact email"})
        s5 = copilot.respond_structured(None, msgs, apps_ws=convo_ws)
        check("turn 5: asks which inbox(es) to enable for",
              s5["feature_request"]["questions_structured"][0]["slot"]
              == "feature_setup.inboxes")

        msgs.append({"role": "assistant", "content": s5["draft"]})
        msgs.append({"role": "user", "content": "enable it for the support inbox"})
        s6 = copilot.respond_structured(None, msgs, apps_ws=convo_ws)
        check("turn 6: complete", s6["status"] == "complete")
        check("turn 6: no fake rule JSON alongside the feature",
              s6["rule"] is None and s6["test_run"] is None)
        prose = copilot.respond(None, msgs, apps_ws=convo_ws)
        check("turn 6: prose confirms by name, never asks an automation question",
              schema.FEATURES[FEATURE_ID]["name"] in prose)
        check("turn 6: prose names the inbox it's enabled for, not a bare 'enabled'",
              "Support" in prose)
    finally:
        router.classify = original_classify
        extract.extract = original_extract

    print(f"track A unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
