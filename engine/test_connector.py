"""Connector recipe tests: the one validated Salesforce CSM auto-assign
recipe, end to end through validator.py + executor.py + features.py — all
pure code, no LLM call, so this runs without an OPENAI_API_KEY.

Covers the five cases called for the first connector pass:
  1. happy path (validator complete, executor assigns the right CSM)
  2. CSM-vs-AE role filter (an account with BOTH roles must resolve to the
     CSM, never the AE)
  3. no-CSM clean failure (an account with only an AE: no exception, a
     structured "no_match", nothing assigned)
  4. provenance rejection (a test_contact_email not in the user's own words
     is scrubbed and re-asked, exactly like any other free-text value)
  5. no-match escalation for anything else

Case 5 is extraction-time behavior (extract.py routing a non-matching ask to
unsupported_requests rather than inventing a recipe id) — that requires a
live LLM call this sandbox has no OPENAI_API_KEY for. What CAN be verified
here without the LLM is the downstream half: validator.py correctly surfaces
an unsupported_requests entry once extraction produces one. See the
`test_no_match_escalation_downstream` case below, and re-run this suite's
LLM-dependent sibling (eval/connector-eval-set.jsonl via cli.py) once a key
is available to close the loop end to end.

Also covers Track A (features.py) prerequisite gating, since it shares the
same connected_apps.py mechanism as the connector's prerequisite checks.

Run: python3 test_connector.py
"""
import sys

import connected_apps
import executor
import features
import salesforce_mock
import schema
import validator

APPS_WS = connected_apps.load()
RECIPE_ID = "salesforce_account_csm_autoassign"


def _connector_spec(test_contact_email):
    return {"trigger": "new_conversation_inbound", "scope_confirmed": True,
            "condition_groups": [],
            "actions": [{"type": "connector", "recipe": RECIPE_ID,
                        "test_contact_email": test_contact_email}]}


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    # ---- 1. happy path ------------------------------------------------------
    convo = ("assign new conversations to the account's CSM automatically, "
             "test with jordan@acme.example")
    spec = _connector_spec("jordan@acme.example")
    res = validator.validate(spec, convo, apps_ws=APPS_WS)
    check("happy path: validator complete", res["status"] == "complete")
    check("happy path: no errors/missing", not res["errors"] and not res["missing"])
    run_result = executor.test_run(RECIPE_ID, "jordan@acme.example")
    check("happy path: executor status ok", run_result["status"] == "ok")
    check("happy path: assigned to the CSM email",
          run_result["final"] == {"type": "assign", "target": "priya.shah@hiver.example"})
    check("happy path: raw responses captured for every api_call",
          all("response" in s for s in run_result["steps"] if s["kind"] == "api_call"))

    # ---- 2. CSM-vs-AE role filter --------------------------------------------
    # Acme has BOTH a CSM (Priya Shah) and an AE (Marcus Lee) on its team —
    # the recipe must resolve to the CSM only, at both layers:
    team_response = salesforce_mock.get_account_team_csm("001A1")
    check("role filter (mock layer): exactly one record", team_response["totalSize"] == 1)
    check("role filter (mock layer): it's the CSM, not the AE",
          team_response["records"][0]["role"] == "CSM"
          and team_response["records"][0]["name"] == "Priya Shah")
    full_team = salesforce_mock.get_account_team("001A1")
    check("fixture sanity: Acme really does have an AE too (else this test proves nothing)",
          any(m["role"] == "AE" for m in full_team["records"]))
    check("role filter (executor layer): never picks the AE",
          run_result["final"]["target"] != "marcus.lee@hiver.example")

    # ---- 3. no-CSM clean failure ---------------------------------------------
    # Globex has only an AE, no CSM — the chain must stop cleanly, not throw.
    globex_convo = ("assign new conversations to the account's CSM automatically, "
                    "test with sam@globex.example")
    globex_spec = _connector_spec("sam@globex.example")
    globex_res = validator.validate(globex_spec, globex_convo, apps_ws=APPS_WS)
    check("no-CSM: still a legally complete RULE (the gap is in the test data, "
          "not the spec)", globex_res["status"] == "complete")
    globex_run = executor.test_run(RECIPE_ID, "sam@globex.example")
    check("no-CSM: clean no_match status, not an exception", globex_run["status"] == "no_match")
    check("no-CSM: nothing assigned", globex_run["final"] is None)
    check("no-CSM: reason names the account-team lookup",
          "get_account_team_csm" in globex_run["reason"])

    # ---- unknown contact: same clean-failure shape, earlier in the chain -----
    unknown_run = executor.test_run(RECIPE_ID, "nobody@nowhere.example")
    check("unknown contact: clean no_match", unknown_run["status"] == "no_match")
    check("unknown contact: only the first step ran",
          len(unknown_run["steps"]) == 1 and unknown_run["steps"][0]["op"]
          == "find_contact_by_email")

    # ---- 4. provenance rejection ---------------------------------------------
    # the admin never wrote this email anywhere in the conversation — it must
    # be scrubbed and re-asked, exactly like a hallucinated tag/assignee.
    bare_convo = "assign new conversations to the account's CSM automatically"
    ghost_spec = _connector_spec("ghost@unstated.example")
    res = validator.validate(ghost_spec, bare_convo, apps_ws=APPS_WS)
    check("provenance: unstated email caught as hallucinated",
          res["hallucinated"] and res["hallucinated"][0]["value"] == "ghost@unstated.example")
    check("provenance: rule is not complete", res["status"] == "needs_info")
    check("provenance: re-asks for the test email",
          any("test" in q.lower() and "email" in q.lower() for q in res["questions"]))
    scrubbed = validator.scrub(ghost_spec, res)
    check("provenance: scrubbed from the draft",
          scrubbed["actions"][0]["test_contact_email"] is None)

    # ---- 5. no-match escalation (downstream half; see module docstring) -----
    escalated_spec = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
                      "condition_groups": [], "actions": [],
                      "unsupported_requests": [schema.UNSUPPORTED["connector_other"]]}
    res = validator.validate(escalated_spec, "when a case closes in Zendesk, tag it",
                             apps_ws=APPS_WS)
    check("no-match escalation: surfaced as unsupported, not invented",
          schema.UNSUPPORTED["connector_other"] in res["unsupported"])
    check("no-match escalation: no connector action was fabricated",
          not any(a.get("type") == "connector" for a in escalated_spec["actions"]))

    # ---- recipe existence / prerequisites ------------------------------------
    bad_recipe = _connector_spec("jordan@acme.example")
    bad_recipe["actions"][0]["recipe"] = "not_a_real_recipe"
    res = validator.validate(bad_recipe, convo, apps_ws=APPS_WS)
    check("unknown recipe id is an error", res["status"] == "invalid" and res["errors"])

    unmet_ws = {"connected_apps": {"salesforce": {"connected": False, "prerequisites": {}}}}
    res = validator.validate(spec, convo, apps_ws=unmet_ws)
    check("unmet prerequisites block the rule", res["status"] == "invalid")
    check("unmet prerequisites name what's missing",
          any("Salesforce" in e for e in res["errors"]))

    res_no_ctx = validator.validate(spec, convo, apps_ws=None)
    check("no apps_ws context skips the prerequisite check (eval/CLI compatibility)",
          res_no_ctx["status"] == "complete")

    # ---- missing recipe -> a human-labeled choice question, not a raw id -----
    no_recipe_spec = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
                      "condition_groups": [],
                      "actions": [{"type": "connector",
                                   "test_contact_email": "jordan@acme.example"}]}
    res = validator.validate(no_recipe_spec, convo, apps_ws=APPS_WS)
    recipe_q = next((q for q in res["questions_structured"]
                     if q["slot"] == "actions[0].recipe"), None)
    check("missing recipe is asked", recipe_q is not None)
    check("missing recipe question uses the human name, not the raw id",
          recipe_q and recipe_q["options"]
          and recipe_q["options"][0]["value"] != RECIPE_ID
          and "CSM" in recipe_q["options"][0]["value"])

    # ---- Track A: feature prerequisite gating (shares connected_apps.py) ----
    ok = features.enable_feature("salesforce_account_contact_details", APPS_WS)
    check("Track A: enables when prerequisites are met", ok["status"] == "complete")
    disconnected_ws = {"connected_apps": {}}
    blocked = features.enable_feature("salesforce_account_contact_details", disconnected_ws)
    check("Track A: blocked when Salesforce isn't connected", blocked["status"] == "invalid")
    unknown = features.enable_feature("not_a_real_feature", APPS_WS)
    check("Track A: unknown feature id is an error, not a silent no-op",
          unknown["status"] == "invalid")

    print(f"connector unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
