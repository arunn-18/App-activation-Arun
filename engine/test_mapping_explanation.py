"""Tests for the requested conversational step this engine didn't have
before: identify the usecase, map it to the catalog of capabilities, and
SAY the mapping out loud — "you want X, I can do that via Y, here's how" —
before diving into setup/rule-building questions. See copilot.py's
_mapping_explanation() for the composing logic and _turn()'s
is_first_turn gate for when it fires.

Deliberately NOT a new catalog file: the explanation is composed entirely
from data that already exists (apps/schema.py's FEATURES, automation/
schema.py's RECIPES/NATIVE_ACTIONS, a custom_plan's own plan_summary) — the
same "answer only from schema.py, never invented" discipline docent.py's
capability answers already follow.

router.classify()/apps.extract.extract()/automation.extract.extract() are
monkeypatched throughout — same reasoning as test_track_a.py's and
test_connector.py's own module docstrings: this only proves the CODE-side
gating and composition, not a live model's ability to identify a usecase.

Run: python3 test_mapping_explanation.py
"""
import sys

import connected_apps
import copilot
import router
from apps import extract as apps_extract
from automation import extract as automation_extract

FEATURE_ID = "salesforce_account_contact_details"
RECIPE_ID = "salesforce_account_csm_autoassign"
NATIVE_ID = "clickup_create_task"


def _connected_salesforce_ws():
    ws = connected_apps.load()
    e = ws["connected_apps"]["salesforce"]
    e["connected"] = True
    for p in e["prerequisites"]:
        e["prerequisites"][p] = True
    return ws


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    # ---- Track A: turn 1 explains, turn 2 doesn't repeat itself -------------
    original_router_classify = router.classify
    original_apps_extract = apps_extract.extract

    def fake_app_setup_classify(client, messages, model=None):
        return {"intent_summary": "test", "track": "app_setup",
                "capability_question": None, "no_intent": None}

    def fake_feature_extract(client, messages, model=None):
        return {"intent_summary": "test", "feature": FEATURE_ID, "connect_requested": True,
                "objects": None, "account_fields": None, "contact_fields": None,
                "inboxes": None, "closing": False, "unmappable": []}

    router.classify = fake_app_setup_classify
    apps_extract.extract = fake_feature_extract
    try:
        ws = _connected_salesforce_ws()
        msgs1 = [{"role": "user", "content": "set up salesforce account cards"}]
        s1 = copilot.respond_structured(None, msgs1, apps_ws=ws)
        check("Track A turn 1: names the matched feature and its own description",
              s1["mapping_explanation"] is not None
              and "View account & contact details" in s1["mapping_explanation"]
              and "CSM" in s1["mapping_explanation"])
        check("Track A turn 1: prose leads with the same explanation",
              copilot.respond(None, msgs1, apps_ws=ws).startswith(
                  "This looks like a fit for **View account & contact details**"))

        msgs2 = msgs1 + [{"role": "assistant", "content": s1["draft"]},
                         {"role": "user", "content": "yes, connect salesforce"}]
        s2 = copilot.respond_structured(None, msgs2, apps_ws=ws)
        check("Track A turn 2: does NOT re-explain — a follow-up, not a fresh match",
              s2["mapping_explanation"] is None)
    finally:
        router.classify = original_router_classify
        apps_extract.extract = original_apps_extract

    # ---- Track A: the app name is read from the matched feature, not -------
    # ---- hardcoded — a real bug found live: every feature match said -------
    # ---- "an existing Salesforce app capability" even for ClickUp ----------
    clickup_explanation = copilot._mapping_explanation(
        {}, {"feature_id": "clickup_create_task_from_hiver"})
    check("Track A: a ClickUp feature match names ClickUp, not Salesforce",
          clickup_explanation is not None
          and "ClickUp" in clickup_explanation
          and "Salesforce" not in clickup_explanation)
    salesforce_explanation = copilot._mapping_explanation(
        {}, {"feature_id": FEATURE_ID})
    check("Track A: a Salesforce feature match still names Salesforce",
          salesforce_explanation is not None and "Salesforce" in salesforce_explanation)

    # ---- Track B: recipe, native action, and custom_plan each get named ----
    original_automation_extract = automation_extract.extract

    def _automation_classify(client, messages, model=None):
        return {"intent_summary": "test", "track": "automation",
                "capability_question": None, "no_intent": None}

    def _base_action(**overrides):
        action = {"type": "connector", "recipe": None, "native_action_id": None,
                  "target_name": None, "title_hint": None, "test_contact_email": None,
                  "custom_plan": None}
        action.update(overrides)
        return {"intent_summary": "test", "trigger": "new_conversation_inbound",
                "scope_confirmed": True, "condition_groups": [], "actions": [action],
                "ai_extract": None, "unsupported_requests": [], "closing": False,
                "unmappable": []}

    router.classify = _automation_classify

    automation_extract.extract = lambda client, messages, model=None, ws=None, on_event=None, app=None: (
        _base_action(recipe=RECIPE_ID))
    try:
        msgs = [{"role": "user", "content": "assign new conversations to the account CSM"}]
        s = copilot.respond_structured(None, msgs)
        check("Track B recipe: names the matched recipe and its own description",
              s["mapping_explanation"] is not None
              and "Auto-assign to the account's CSM" in s["mapping_explanation"])
    finally:
        automation_extract.extract = original_automation_extract

    automation_extract.extract = lambda client, messages, model=None, ws=None, on_event=None, app=None: (
        _base_action(native_action_id=NATIVE_ID))
    try:
        msgs = [{"role": "user", "content": "create a clickup task for this conversation"}]
        s = copilot.respond_structured(None, msgs)
        check("Track B native action: names the matched native action, flags it as "
              "built-in (not composed)",
              s["mapping_explanation"] is not None
              and "Create tasks automatically via automation" in s["mapping_explanation"]
              and "built-in ClickUp action" in s["mapping_explanation"])
    finally:
        automation_extract.extract = original_automation_extract

    plan = {"app": "salesforce", "plan_summary": "Assign to the Account Owner",
            "steps": [], "terminal": {"kind": "assign", "target": None, "tags": None}}
    automation_extract.extract = lambda client, messages, model=None, ws=None, on_event=None, app=None: (
        _base_action(custom_plan=plan))
    try:
        msgs = [{"role": "user", "content": "assign to the account owner instead of the csm"}]
        s = copilot.respond_structured(None, msgs)
        check("Track B custom_plan: names it as composed (no ready-made action), "
              "quotes the plan's own summary",
              s["mapping_explanation"] is not None
              and "composed Salesforce lookup" in s["mapping_explanation"]
              and "Assign to the Account Owner" in s["mapping_explanation"])
    finally:
        automation_extract.extract = original_automation_extract

    # ---- nothing matched yet -> nothing to explain --------------------------
    automation_extract.extract = lambda client, messages, model=None, ws=None, on_event=None, app=None: (
        _base_action())
    try:
        msgs = [{"role": "user", "content": "tag emails from acme.com as VIP"}]
        s = copilot.respond_structured(None, msgs)
        check("no connector action matched -> mapping_explanation is None, "
              "not a fabricated capability",
              s["mapping_explanation"] is None)
    finally:
        automation_extract.extract = original_automation_extract
        router.classify = original_router_classify

    print(f"mapping explanation unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
