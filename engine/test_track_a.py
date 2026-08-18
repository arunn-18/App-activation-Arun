"""Track A tests: an app_feature ask (schema.FEATURES) must resolve through
features.py, NEVER through the automation validator — a real regression this
guards against (a live run showed "set up Salesforce account cards" being
forced into a WHEN/IF/THEN automation questionnaire because extraction had
no Track A vocabulary and copilot.py had no branch for it).

Pure code, no LLM call, except where noted — extract.extract() is
monkeypatched to isolate copilot.py's ROUTING logic (does app_feature take
the feature path, not the validator path?) from the LLM's own judgment of
when to set it, which is a separate, not-yet-verifiable-here concern (see
test_connector.py's module docstring for the same caveat on Track B).

Run: python3 test_track_a.py
"""
import sys

import connected_apps
import copilot
import extract
import features
import schema

APPS_WS = connected_apps.load()
FEATURE_ID = "salesforce_account_contact_details"


def _spec(app_feature):
    return {
        "intent_summary": "test", "trigger": None, "scope_confirmed": False,
        "condition_groups": [], "actions": [], "ai_extract": None,
        "unsupported_requests": [], "closing": False,
        "capability_question": None, "no_intent": None, "unmappable": [],
        "app_feature": app_feature,
    }


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    # ---- feature_request_result: the routing decision itself, no LLM involved
    check("app_feature unset -> not Track A",
          copilot.feature_request_result(_spec(None), APPS_WS) is None)
    r = copilot.feature_request_result(_spec(FEATURE_ID), APPS_WS)
    check("app_feature set + prerequisites met -> complete",
          r is not None and r["status"] == "complete")
    check("resolved feature carries the real name/description",
          r["feature"]["name"] == schema.FEATURES[FEATURE_ID]["name"])

    disconnected_ws = {"connected_apps": {}}
    r2 = copilot.feature_request_result(_spec(FEATURE_ID), disconnected_ws)
    check("prerequisites unmet -> invalid, not silently allowed",
          r2["status"] == "invalid" and r2["errors"])

    r3 = copilot.feature_request_result(_spec(FEATURE_ID), None)
    check("no apps_ws context -> invalid, not a crash",
          r3["status"] == "invalid")

    r4 = copilot.feature_request_result(_spec("not_a_real_feature"), APPS_WS)
    check("unknown feature id -> invalid via features.py, not a KeyError",
          r4["status"] == "invalid")

    # ---- copilot._turn / respond_structured: the actual regression this
    # file exists for — app_feature must NEVER reach validator.validate(),
    # which only understands trigger/conditions/actions and would otherwise
    # ask "when should this run?" for a request that was never an automation.
    original_extract = extract.extract

    def fake_extract(client, messages, model=None, ws=None, on_event=None):
        return _spec(FEATURE_ID)

    extract.extract = fake_extract
    try:
        messages = [{"role": "user",
                    "content": "set up salesforce account cards for my shared mailbox"}]
        state = copilot.respond_structured(None, messages, apps_ws=APPS_WS)
        check("routes to the feature track, not automation",
              state["track"] == "feature")
        check("no fake trigger/conditions/actions rendered",
              state["rule"] is None and state["spec"]["trigger"] is None
              and state["spec"]["actions"] == [])
        check("no automation questions ('when should this run?') asked",
              not state["questions"])
        check("draft names the feature, not WHEN/IF/THEN",
              "APP FEATURE" in state["draft"] and "WHEN" not in state["draft"])
        check("status reflects the feature, not a needs_info automation",
              state["status"] == "complete")

        prose = copilot.respond(None, messages, apps_ws=APPS_WS)
        check("prose never asks the automation trigger question",
              "when should this run" not in prose.lower())
        check("prose confirms the feature by name",
              schema.FEATURES[FEATURE_ID]["name"] in prose)
    finally:
        extract.extract = original_extract

    # ---- Track A and Track B stay mutually exclusive (extract.py rule 20) —
    # a defensive check on copilot's OWN behavior, not the model's: even if a
    # spec somehow carried both, the feature path takes priority and no rule
    # JSON is emitted alongside it.
    mixed = _spec(FEATURE_ID)
    mixed["actions"] = [{"type": "add_tag", "tags": ["VIP"]}]
    mixed["trigger"] = "new_conversation_inbound"

    def fake_extract_mixed(client, messages, model=None, ws=None, on_event=None):
        return mixed

    extract.extract = fake_extract_mixed
    try:
        state = copilot.respond_structured(None, messages, apps_ws=APPS_WS)
        check("app_feature wins over stray rule content — no rule JSON emitted",
              state["rule"] is None and state["track"] == "feature")
    finally:
        extract.extract = original_extract

    print(f"track A unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
