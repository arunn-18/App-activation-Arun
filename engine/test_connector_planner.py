"""Dynamic connector plan tests: automation/planner.py + plan_validator.py +
executor.py's generic query op, for use cases that have NO hand-written
schema.RECIPES entry — the model composes its own chain from the
salesforce_schema.py object/field catalog instead of following a fixed one.
All pure code, no LLM call: the tool-calling composition step itself
(automation/extract.py's rule 19b, run through a live model) is a separate,
not-yet-verifiable-here concern, exactly like test_connector.py's own
module docstring already notes for the fixed recipe's routing half. What
CAN be verified here without an LLM is everything downstream of "the model
proposed this plan": structural rejection of an unsafe one, full end-to-end
execution of a safe one, and the stricter completeness bar a plan gets that
a hand-vetted recipe doesn't need.

Two use cases exercise the dynamic path end to end, proving genericity
rather than a single cherry-picked example:
  1. assign to the Account's Owner (not the CSM) — a 2-step lookup ending
     in `assign`
  2. tag the conversation with an open Case's priority — a 2-step lookup
     ending in `add_tag`

Run: python3 test_connector_planner.py
"""
import sys

import connected_apps
import copilot
from automation import executor, plan_validator, validator

OWNER_PLAN = {
    "app": "salesforce", "plan_summary": "Assign to the Account Owner instead of the CSM.",
    "steps": [
        {"object": "Contact", "where": [{"field": "email", "eq": "{{contact_email}}"}],
         "extract_variables": [{"variable": "account_id", "field": "account_id"}]},
        {"object": "Account", "where": [{"field": "account_id", "eq": "{{account_id}}"}],
         "extract_variables": [{"variable": "owner_email", "field": "owner_email"}]},
    ],
    "terminal": {"kind": "assign", "target": "{{owner_email}}", "tags": []},
}

CASE_TAG_PLAN = {
    "app": "salesforce", "plan_summary": "Tag with the account's open Case priority.",
    "steps": [
        {"object": "Contact", "where": [{"field": "email", "eq": "{{contact_email}}"}],
         "extract_variables": [{"variable": "account_id", "field": "account_id"}]},
        {"object": "Case", "where": [{"field": "account_id", "eq": "{{account_id}}"}],
         "extract_variables": [{"variable": "priority", "field": "priority"}]},
    ],
    "terminal": {"kind": "add_tag", "target": None, "tags": ["{{priority}}"]},
}


def _connected_apps_ws():
    ws = connected_apps.load()
    entry = ws["connected_apps"]["salesforce"]
    entry["connected"] = True
    for p in entry["prerequisites"]:
        entry["prerequisites"][p] = True
    return ws


def _spec(plan, test_email):
    return {
        "trigger": "new_conversation_inbound", "scope_confirmed": True, "condition_groups": [],
        "actions": [{"type": "connector", "recipe": None, "custom_plan": plan,
                    "test_contact_email": test_email}],
        "ai_extract": None, "unsupported_requests": [], "closing": False, "unmappable": [],
        "intent_summary": "test",
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

    apps_ws = _connected_apps_ws()

    # ---- structural guardrails (plan_validator.validate_plan) ----------------
    unknown_field = {"app": "salesforce", "plan_summary": "x", "steps": [
        {"object": "Contact", "where": [{"field": "ssn", "eq": "{{contact_email}}"}],
         "extract_variables": [{"variable": "account_id", "field": "account_id"}]}],
        "terminal": {"kind": "assign", "target": "{{account_id}}", "tags": []}}
    check("unknown field is rejected, not silently accepted",
          plan_validator.validate_plan(unknown_field, {"contact_email": ""}))

    non_assignable = {"app": "salesforce", "plan_summary": "x", "steps": [
        {"object": "Contact", "where": [{"field": "email", "eq": "{{contact_email}}"}],
         "extract_variables": [{"variable": "account_id", "field": "account_id"}]},
        {"object": "Case", "where": [{"field": "account_id", "eq": "{{account_id}}"}],
         "extract_variables": [{"variable": "subj", "field": "subject"}]}],
        "terminal": {"kind": "assign", "target": "{{subj}}", "tags": []}}
    errs = plan_validator.validate_plan(non_assignable, {"contact_email": ""})
    check("a real field not marked assignable is rejected as an assign source",
          errs and "Case.subject" in errs[0])

    forward_ref = {"app": "salesforce", "plan_summary": "x", "steps": [
        {"object": "Account", "where": [{"field": "account_id", "eq": "{{account_id}}"}],
         "extract_variables": [{"variable": "owner_email", "field": "owner_email"}]}],
        "terminal": {"kind": "assign", "target": "{{owner_email}}", "tags": []}}
    check("a step referencing a variable no earlier step extracted is rejected",
          plan_validator.validate_plan(forward_ref, {"contact_email": ""}))

    too_many_steps = {"app": "salesforce", "plan_summary": "x",
                      "steps": [{"object": "Contact", "where": [], "extract_variables": []}] * 5,
                      "terminal": {"kind": "assign", "target": "{{x}}", "tags": []}}
    check("a plan over MAX_PLAN_STEPS is rejected",
          plan_validator.validate_plan(too_many_steps, {"contact_email": ""}))

    literal_terminal = {"app": "salesforce", "plan_summary": "x", "steps": [
        {"object": "Contact", "where": [{"field": "email", "eq": "{{contact_email}}"}],
         "extract_variables": [{"variable": "account_id", "field": "account_id"}]}],
        "terminal": {"kind": "assign", "target": "not-a-var@evil.example", "tags": []}}
    check("a terminal value that's a literal, not an extracted variable, is rejected",
          plan_validator.validate_plan(literal_terminal, {"contact_email": ""}))

    unknown_object = {"app": "salesforce", "plan_summary": "x", "steps": [
        {"object": "Lead", "where": [{"field": "email", "eq": "{{contact_email}}"}],
         "extract_variables": [{"variable": "x", "field": "y"}]}],
        "terminal": {"kind": "assign", "target": "{{x}}", "tags": []}}
    check("an object outside the catalog is rejected",
          plan_validator.validate_plan(unknown_object, {"contact_email": ""}))

    check("a structurally valid plan passes with zero errors",
          plan_validator.validate_plan(OWNER_PLAN, {"contact_email": ""}) == [])
    check("the case-tag plan also passes with zero errors",
          plan_validator.validate_plan(CASE_TAG_PLAN, {"contact_email": ""}) == [])

    # ---- use case 1: assign to Account Owner (no RECIPES entry involved) -----
    r1 = validator.validate(_spec(OWNER_PLAN, "jordan@acme.example"),
                            "assign to the account owner instead of the CSM, test with "
                            "jordan@acme.example", apps_ws=apps_ws)
    check("owner plan: structurally valid + real test run -> complete",
          r1["status"] == "complete" and not r1["errors"])
    run1 = executor.test_run_plan(OWNER_PLAN, "jordan@acme.example")
    check("owner plan executes for real against the mock",
          run1["status"] == "ok" and run1["final"]["target"] == "marcus.lee@hiver.example")

    # ---- use case 2: tag with the account's open Case priority ---------------
    r2 = validator.validate(_spec(CASE_TAG_PLAN, "jordan@acme.example"),
                            "tag with the case priority when the account has an open case, "
                            "test with jordan@acme.example", apps_ws=apps_ws)
    check("case-tag plan: structurally valid + real test run -> complete",
          r2["status"] == "complete" and not r2["errors"])
    run2 = executor.test_run_plan(CASE_TAG_PLAN, "jordan@acme.example")
    check("case-tag plan executes for real against the mock",
          run2["status"] == "ok" and run2["final"]["tags"] == ["High"])

    # ---- stricter bar: a validated-looking plan still must PROVE itself ------
    # (unlike a hand-vetted RECIPES chain, where a clean no_match is an
    # acceptable outcome because the chain itself was already proven correct
    # by this suite's sibling, test_connector.py)
    r3 = validator.validate(_spec(OWNER_PLAN, "nobody@nowhere.example"),
                            "assign to the account owner, test with nobody@nowhere.example",
                            apps_ws=apps_ws)
    check("a plan whose test run doesn't succeed is NOT marked complete",
          r3["status"] != "complete" and r3["errors"])

    # ---- prerequisites still apply to a dynamic plan --------------------------
    disconnected_ws = connected_apps.load()
    r4 = validator.validate(_spec(OWNER_PLAN, "jordan@acme.example"),
                            "assign to the account owner, test with jordan@acme.example",
                            apps_ws=disconnected_ws)
    check("a dynamic plan is blocked when Salesforce isn't connected",
          r4["status"] != "complete" and r4["errors"])

    # ---- neither recipe nor a valid custom_plan: the original fallback question
    empty_action_spec = _spec(None, "jordan@acme.example")
    empty_action_spec["actions"][0]["custom_plan"] = None
    r5 = validator.validate(empty_action_spec, "do something with salesforce",
                            apps_ws=apps_ws)
    check("neither recipe nor custom_plan present -> asks which app automation, "
          "doesn't silently pass or crash",
          r5["status"] == "needs_info"
          and r5["questions_structured"]
          and r5["questions_structured"][0]["slot"] == "actions[0].recipe")

    # ---- rendering: copilot.py shows the dynamic plan's own terminal, not the
    # fixed recipe's, and to_final_json carries the real plan + derived fields
    spec = _spec(OWNER_PLAN, "jordan@acme.example")
    draft = copilot.render_structure(spec)
    check("draft shows the plan's own summary and terminal assign target",
          "Assign to the Account Owner" in draft and "{{owner_email}}" in draft)
    final = copilot.to_final_json(spec)
    check("exported JSON carries the raw custom_plan and derived assigns_to",
          final["actions"][0]["custom_plan"] == OWNER_PLAN
          and final["actions"][0]["assigns_to"] == "{{owner_email}}"
          and final["actions"][0]["tags_with"] is None)
    test_run_line = copilot._render_test_run(copilot.connector_test_run(spec))
    check("connector_test_run runs the dynamic plan, not just fixed recipes",
          "marcus.lee@hiver.example" in test_run_line)

    print(f"connector planner unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
