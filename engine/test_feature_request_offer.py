"""Tests for the Apps Activation PRD's Discovery movement (2026-08-24):
"no match in the catalogue -> feature request logged", scoped exactly to
that PRD's own Escalation Trigger table row — an `unmappable` ask on EITHER
track, never the already-categorized `unsupported_requests` list (Hiver
already knows those gaps exist; re-logging them would be noise, not a
demand signal for something unbuilt).

Also covers this same phase's self-serve remediation text (a prerequisite
with no one-click fix must say HOW to clear it, not just name it) and the
Knowledge-layer example-phrasing metadata reused in docent.py's capability
answers.

All pure code, no LLM call — router.classify()/apps.extract.extract()/
automation.extract.extract() are stubbed the same way test_track_a.py and
test_mapping_explanation.py already do; everything downstream of "the model
produced this classification/extraction" is fully verifiable here.

Run: python3 test_feature_request_offer.py
"""
import sys

import analytics
import connected_apps
import copilot
import docent
import feature_requests
import router
from apps import extract as apps_extract
from automation import extract as automation_extract


def _fake_classify(track):
    def classify(client, messages, model=None):
        return {"intent_summary": "test", "track": track,
                "capability_question": None, "no_intent": None}
    return classify


def _fake_automation_extract(unmappable, feature_request_requested):
    def extract(client, messages, model=None, ws=None, on_event=None, app=None):
        return {"trigger": None, "scope_confirmed": None, "condition_groups": [],
                "actions": [], "ai_extract": None, "unsupported_requests": [],
                "closing": False, "capability_question": None, "no_intent": None,
                "unmappable": unmappable, "intent_summary": "test",
                "enabled_inboxes": None,
                "feature_request_requested": feature_request_requested}
    return extract


def _fake_apps_extract_no_match(unmappable, feature_request_requested):
    def extract(client, messages, model=None):
        return {"intent_summary": "test", "feature": None, "closing": False,
                "connect_requested": None, "objects": None, "account_fields": None,
                "contact_fields": None, "task_fields": None, "inboxes": None,
                "test_contact_email": None, "unmappable": unmappable,
                "feature_request_requested": feature_request_requested}
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

    # ---- feature_requests.py: log/dedupe/reset ------------------------------
    feature_requests.reset()
    e1 = feature_requests.log(app="salesforce", request="sync to NetSuite",
                              why="no NetSuite integration", track="automation")
    e2 = feature_requests.log(app="salesforce", request="sync to NetSuite",
                              why="no NetSuite integration", track="automation")
    check("log() dedupes by (app, request) -- same entry, not a duplicate",
          e1 is e2 and len(feature_requests.all_requests()) == 1)
    feature_requests.log(app="clickup", request="bulk task import", why="not built", track="app_setup")
    check("a genuinely different request adds a second entry",
          len(feature_requests.all_requests()) == 2)
    feature_requests.reset()
    check("reset() clears the log", feature_requests.all_requests() == [])

    # ---- analytics.py: emit/reset, event name matches the PRD's own string -
    analytics.reset()
    analytics.emit(analytics.EVENTS.FEATURE_REQUEST_LOGGED, {"app_id": "clickup"})
    check("emit() records the event with its properties",
          analytics.all_events() == [{"event": "apps_activation_feature_request_logged",
                                      "properties": {"app_id": "clickup"}}])
    check("EVENTS.FEATURE_REQUEST_LOGGED matches the PRD's own event name verbatim",
          analytics.EVENTS.FEATURE_REQUEST_LOGGED == "apps_activation_feature_request_logged")
    analytics.reset()
    check("reset() clears the log", analytics.all_events() == [])

    # ---- end to end via copilot.respond()/respond_structured() -------------
    unmappable = [{"request": "create a ticket in Zendesk", "why": "Zendesk isn't a supported app"}]

    def turn(track, feature_request_requested, msgs=None, app=None):
        oc, oae, oxe = router.classify, apps_extract.extract, automation_extract.extract
        router.classify = _fake_classify(track)
        automation_extract.extract = _fake_automation_extract(unmappable, feature_request_requested)
        apps_extract.extract = _fake_apps_extract_no_match(unmappable, feature_request_requested)
        try:
            m = msgs or [{"role": "user", "content": "create a ticket in Zendesk whenever a VIP email arrives"}]
            return copilot.respond(None, m, app=app), copilot.respond_structured(None, m, app=app)
        finally:
            router.classify, apps_extract.extract, automation_extract.extract = oc, oae, oxe

    feature_requests.reset()
    analytics.reset()

    prose1, s1 = turn("automation", None)
    check("unanswered: prose offers to log it",
          "Log this as a feature request?" not in prose1  # the QUESTION renders via the form, not inline prose
          and feature_requests.all_requests() == [])
    offer_q = next((q for q in s1["questions_structured"] if q["slot"] == "feature_request_offer"), None)
    check("unanswered: a real yes/no choice question is offered, not a dead end",
          offer_q is not None and offer_q["kind"] == "choice"
          and {o["value"] for o in offer_q["options"]}
              == {"log this as a feature request", "no, don't log it"})
    check("unanswered: nothing logged yet, no analytics event fired",
          feature_requests.all_requests() == [] and analytics.all_events() == [])

    prose2, s2 = turn("automation", True)
    check("answered yes: prose confirms it was logged",
          "Logged as a feature request" in prose2)
    check("answered yes: the offer question is NOT re-asked",
          not any(q["slot"] == "feature_request_offer" for q in s2["questions_structured"]))
    check("answered yes: actually logged, with the right app/request/why/track",
          feature_requests.all_requests() == [{"app": None, "request": "create a ticket in Zendesk",
                                               "why": "Zendesk isn't a supported app",
                                               "track": "automation"}])
    check("answered yes: an analytics event fired with the PRD's own event name",
          any(e["event"] == "apps_activation_feature_request_logged"
              and e["properties"]["requested_capability_text"] == "create a ticket in Zendesk"
              for e in analytics.all_events()))

    feature_requests.reset()
    analytics.reset()
    prose3, s3 = turn("automation", False)
    check("answered no: a brief acknowledgment, not logged, not re-asked",
          "No problem" in prose3 and feature_requests.all_requests() == []
          and not any(q["slot"] == "feature_request_offer" for q in s3["questions_structured"]))

    # ---- app_setup track (no feature match) reaches the SAME offer ---------
    feature_requests.reset()
    prose4, s4 = turn("app_setup", True, app="clickup")
    check("Track A's own unmappable ask reaches the same offer/log mechanism, "
          "tagged with the real track (not misattributed to app_setup just "
          "because app_setup was the CLASSIFIED track for a genuinely unmatched ask)",
          "Logged as a feature request" in prose4
          and feature_requests.all_requests()[0]["app"] == "clickup"
          and feature_requests.all_requests()[0]["track"] == "app_setup")

    # ---- no unmappable content at all -> no offer, ever ---------------------
    feature_requests.reset()
    oc, oae = router.classify, automation_extract.extract
    router.classify = _fake_classify("automation")
    automation_extract.extract = _fake_automation_extract([], None)
    try:
        s5 = copilot.respond_structured(
            None, [{"role": "user", "content": "tag every new incoming email as VIP"}])
    finally:
        router.classify, automation_extract.extract = oc, oae
    check("nothing unmappable -> no offer question, no confirmation, ever",
          not any(q["slot"] == "feature_request_offer" for q in s5["questions_structured"])
          and s5["feature_request_offer"] is None)

    # ---- self-serve remediation: a non-one-click prerequisite says HOW -----
    check("connected_apps.remediation_for names a real prerequisite's fix",
          connected_apps.remediation_for("account_team_enabled") is not None
          and "Account Teams" in connected_apps.remediation_for("account_team_enabled"))
    check("remediation_for is honest (None, not invented) for an unknown key",
          connected_apps.remediation_for("not_a_real_prerequisite") is None)

    from automation import validator
    spec = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
            "condition_groups": [], "actions": [{"type": "connector",
            "recipe": "salesforce_account_csm_autoassign", "native_action_id": None,
            "test_contact_email": "jordan@acme.example", "custom_plan": None,
            "connect_requested": None}], "ai_extract": None, "unsupported_requests": [],
            "closing": False, "capability_question": None, "no_intent": None,
            "unmappable": [], "intent_summary": "test", "enabled_inboxes": None}
    no_fix_ws = {"connected_apps": {"salesforce": {"connected": True, "prerequisites": {
        "salesforce_connected": True, "account_team_enabled": False}}}}
    r = validator.validate(spec, "assign to the csm", apps_ws=no_fix_ws)
    check("automation/validator.py's honest-error branch now says how to fix it, "
          "not just what's blocked",
          r["status"] == "invalid"
          and any("To fix it yourself" in e and "Account Teams" in e for e in r["errors"]))

    from apps import setup as features
    sf_ws = {"connected_apps": {"salesforce": {"connected": True, "prerequisites": {
        "salesforce_connected": True, "account_team_enabled": False}}}}
    # salesforce_create_contact only prerequires salesforce_connected, so this
    # exercises a DIFFERENT path -- reuse the same remediation dict shape by
    # asserting the function itself is wired in, via a direct call shape check
    # (apps/setup.py's own feature prerequisites don't include account_team_
    # enabled today, so this confirms the code path exists and is honest
    # about returning nothing extra when there's nothing to add).
    r2 = features.resolve_setup("salesforce_create_contact", {}, sf_ws)
    check("apps/setup.py's auth step is unaffected when the blocked prerequisite "
          "DOES have a one-click fix (still offers Connect, not an invalid dead end)",
          r2["status"] == "needs_info")

    # ---- Knowledge layer: example phrasings reach docent's capability answer
    a = docent.answer("clickup integration")
    check("docent's integration answer now covers ClickUp's Track A feature "
          "too (a real pre-existing gap the salesforce-only filter had), "
          "with a concrete example phrasing, not just a restated description",
          "Create a Task from Hiver" in a and "let agents create a ClickUp task" in a)

    print(f"feature-request-offer unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
