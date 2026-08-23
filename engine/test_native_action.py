"""Capability 5 (native app-action automations) tests: a connector action's
THIRD mechanism, alongside a hand-vetted RECIPES chain and a dynamically-
composed custom_plan — see automation/schema.py's NATIVE_ACTIONS and
automation/validator.py's connector block for the full three-way split.
All pure code, no LLM call, same reasoning as test_connector.py's own
module docstring: extraction-time routing (a live model choosing
native_action_id over recipe/custom_plan/unsupported) needs a real
OPENAI_API_KEY this sandbox doesn't have; everything downstream of "the
model picked this native action" is fully verifiable here.

clickup_create_task is deliberately the SECOND real app in this engine (the
first outside Salesforce) — proving capability 5 generalizes past one app,
not just asserting it in comments. Onboarding it needed: one
connected_apps.json entry (auth), one NATIVE_ACTIONS entry (schema.py), and
one small mock service (clickup_mock.py) — no engine code changed to add
it, per the "config + a small service module" cost this was built for.

Run: python3 test_native_action.py
"""
import sys

import connected_apps
import copilot
from automation import validator

ACTION_ID = "clickup_create_task"


def _connected_ws():
    ws = connected_apps.load()
    entry = ws["connected_apps"]["clickup"]
    entry["connected"] = True
    for p in entry["prerequisites"]:
        entry["prerequisites"][p] = True
    return ws


def _disconnected_ws():
    return connected_apps.load()  # ships disconnected by default


def _spec(**action_overrides):
    action = {"type": "connector", "native_action_id": ACTION_ID,
              "target_name": None, "title_hint": None, "recipe": None,
              "custom_plan": None, "test_contact_email": None}
    action.update(action_overrides)
    return {"trigger": "new_conversation_inbound", "scope_confirmed": True,
            "condition_groups": [], "actions": [action], "ai_extract": None,
            "unsupported_requests": [], "closing": False,
            "capability_question": None, "no_intent": None, "unmappable": [],
            "intent_summary": "test"}


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    convo = ("create a clickup task in the Support Escalations list "
             "titled Follow up with customer")

    # ---- happy path -----------------------------------------------------------
    connected = _connected_ws()
    spec = _spec(target_name="Support Escalations", title_hint="Follow up with customer")
    r1 = validator.validate(spec, convo, apps_ws=connected)
    check("connected + both params provenance-verified -> complete",
          r1["status"] == "complete" and not r1["errors"])

    # ---- missing required params -----------------------------------------------
    r2 = validator.validate(_spec(), "create a clickup task", apps_ws=connected)
    check("no params yet -> needs_info, asks for both", r2["status"] == "needs_info"
          and {q["slot"] for q in r2["missing"]}
              >= {"actions[0].target_name", "actions[0].title_hint"})

    # ---- provenance: target_name must be in the user's own words --------------
    hallucinated_spec = _spec(target_name="Some Other List",
                              title_hint="Follow up with customer")
    r3 = validator.validate(hallucinated_spec, convo, apps_ws=connected)
    check("target_name not in the user's own words -> scrubbed and re-asked, "
          "not silently trusted",
          r3["status"] == "needs_info"
          and any(m["slot"] == "actions[0].target_name" for m in r3["missing"]))

    # ---- prerequisite gating: same discipline a RECIPES entry gets ------------
    # A live test found the old behavior (a static "must be connected" error,
    # with nothing to click or a clear phrase to type) left the admin stuck —
    # this must be an ACTUAL "Connect ClickUp" question, same shape Track A's
    # own connect step already offers.
    disconnected = _disconnected_ws()
    r4 = validator.validate(spec, convo, apps_ws=disconnected)
    check("ClickUp not connected -> asks to connect, not a dead-end error",
          r4["status"] == "needs_info" and not r4["errors"]
          and r4["questions_structured"][0]["kind"] == "choice"
          and r4["questions_structured"][0]["options"]
              == [{"label": "Connect ClickUp", "value": "connect clickup"}])

    # connect_requested actually flips the connection and moves the flow on.
    connect_spec = {**spec, "actions": [{**spec["actions"][0], "connect_requested": True}]}
    fresh_disconnected = _disconnected_ws()
    r4b = validator.validate(connect_spec, convo, apps_ws=fresh_disconnected)
    check("connect_requested connects ClickUp for real, clearing the gate",
          fresh_disconnected["connected_apps"]["clickup"]["connected"] is True
          and r4b["status"] == "complete")

    r5 = validator.validate(spec, convo, apps_ws=None)
    check("no apps_ws context -> prerequisite check skipped, not failed",
          r5["status"] == "complete")

    # ---- fallback: neither recipe, native action, nor plan present -----------
    empty_spec = _spec()
    empty_spec["actions"][0]["native_action_id"] = None
    r6 = validator.validate(empty_spec, "do something with an app", apps_ws=connected)
    check("nothing present -> offers RECIPES entries AND native actions as choices",
          r6["status"] == "needs_info"
          and r6["questions_structured"]
          and r6["questions_structured"][0]["slot"] == "actions[0].recipe"
          and any(o["label"] == "Create a ClickUp task"
                  for o in r6["questions_structured"][0]["options"]))

    # ---- rendering: draft text, exported JSON, real test-run ------------------
    draft = copilot.render_structure(spec)
    check("draft shows the native action by name and its two params, not a "
          "generic 'connector' line",
          "Create a ClickUp task" in draft and "Support Escalations" in draft
          and "Follow up with customer" in draft)

    final = copilot.to_final_json(spec)
    check("exported JSON carries native_action_id/target_name/title_hint, "
          "and no recipe/custom_plan leftovers",
          final["actions"][0]["native_action_id"] == ACTION_ID
          and final["actions"][0]["target_name"] == "Support Escalations"
          and final["actions"][0]["title_hint"] == "Follow up with customer"
          and final["actions"][0]["recipe"] is None
          and final["actions"][0]["custom_plan"] is None
          and final["actions"][0]["assigns_to"] is None
          and final["actions"][0]["tags_with"] is None)

    test_run = copilot.connector_test_run(spec)
    check("connector_test_run fires the native action even with no "
          "test_contact_email — there's no per-contact lookup to prove",
          test_run is not None and test_run["status"] == "ok"
          and test_run["result"]["list"] == "Support Escalations"
          and test_run["result"]["name"] == "Follow up with customer")

    test_run_line = copilot._render_test_run(test_run)
    check("test-run prose shows the real created-task URL, not a crash on a "
          "chain-shaped 'final' key this result doesn't have",
          test_run_line is not None and "clickup.com" in test_run_line)

    # ---- Apps-panel scoping: vocab must not leak across apps -----------------
    # A live test surfaced this: the Apps panel's own module docstring
    # (serve_apps.py) flagged app-scoping as a "no-op until a second app
    # exists" TODO back when there was only one recipe (Salesforce).
    # clickup_create_task is that second app — this proves the vocab a
    # scoped extraction call actually sees stays within its own app.
    from automation import extract as automation_extract

    clickup_vocab = automation_extract._vocab_block("clickup")
    check("clickup-scoped vocab lists its own native action",
          "clickup_create_task" in clickup_vocab)
    check("clickup-scoped vocab never mentions the Salesforce recipe id "
          "(the ACTIONS line's `recipe=` enum, not just the CONNECTOR "
          "RECIPES listing further down)",
          "salesforce_account_csm_autoassign" not in clickup_vocab)
    check("clickup-scoped vocab drops the Salesforce-only custom_plan "
          "SALESFORCE OBJECTS line entirely -- irrelevant noise for an app "
          "with no Salesforce object model",
          "SALESFORCE OBJECTS" not in clickup_vocab)

    salesforce_vocab = automation_extract._vocab_block("salesforce")
    check("salesforce-scoped vocab never mentions ClickUp's native action",
          "clickup" not in salesforce_vocab.lower())

    unscoped_vocab = automation_extract._vocab_block(None)
    check("unscoped vocab (app=None, the general Automations copilot) keeps "
          "BOTH apps -- that surface legitimately builds automations for "
          "any app or none at all",
          "clickup_create_task" in unscoped_vocab
          and "salesforce_account_csm_autoassign" in unscoped_vocab)

    print(f"native action unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
