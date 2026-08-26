"""Tests for capability 7, "test on a real conversation": instead of (or
alongside) asking an admin to type an arbitrary test email, offer REAL
conversations from the demo mailbox (mailbox.json, via mailbox_lookup.py)
whose sender is a known Salesforce contact, and prove the capability
against that conversation's actual sender — a Track A view feature's real
field values (apps.setup.preview_feature, a courtesy, never blocking
completeness) or a Track B connector's real test-run (the SAME
test_contact_email slot that already existed, now offered as a choice of
real conversations with a free-text fallback, not a behavior change to
what counts as complete).

All pure code, no LLM call — same reasoning as this engine's other
capability test files: which conversation a live model would pick is not
verifiable in this sandbox; everything downstream of "a real email is
available" is.

Run: python3 test_real_conversation.py
"""
import sys

import connected_apps
import copilot
import mailbox_lookup
import salesforce_mock
from apps import setup as features
from automation import validator

FEATURE_ID = "salesforce_account_contact_details"
WRITE_FEATURE_ID = "salesforce_create_contact"
RECIPE_ID = "salesforce_account_csm_autoassign"


def _connected_ws(app="salesforce"):
    ws = connected_apps.load()
    e = ws["connected_apps"][app]
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

    # ---- mailbox_lookup: only REAL matches, most recent first ----------------
    convos = mailbox_lookup.testable_conversations()
    check("only returns conversations whose sender is a real Salesforce contact",
          all("@" in c["from"] for c in convos) and len(convos) >= 3)
    check("sorted most recent first",
          convos == sorted(convos, key=lambda c: c["received_at"], reverse=True))
    check("find_conversation recovers one of them by id",
          mailbox_lookup.find_conversation(convos[0]["id"]) is not None
          and mailbox_lookup.find_conversation(convos[0]["id"])["from"] == convos[0]["from"])
    check("find_conversation returns None for an id that doesn't exist",
          mailbox_lookup.find_conversation("not-a-real-id") is None)

    # ---- Track A: preview_feature() against real data -----------------------
    complete_feature = {
        "id": FEATURE_ID, "app": "salesforce", "name": "View account & contact details",
        "objects": ["Account", "Contact"],
        "fields_by_object": {"Account": ["Account Name", "Account Owner"],
                             "Contact": ["Contact Name", "Contact Email"]},
        "inboxes": ["Support"],
    }
    r1 = features.preview_feature(complete_feature, "jordan@acme.example")
    check("happy path: real Account + Contact field values, not placeholders",
          r1["status"] == "ok"
          and r1["values_by_object"]["Account"]["Account Name"] == "Acme Corp"
          and r1["values_by_object"]["Contact"]["Contact Name"] == "Jordan Kim")

    r2 = features.preview_feature(complete_feature, "nobody@nowhere.example")
    check("unknown contact -> a clean no_match, not an error or fabricated data",
          r2["status"] == "no_match" and "nobody@nowhere.example" in r2["reason"])

    # ---- Track A: resolve_setup() wires test_contact_email in as a courtesy -
    connected = _connected_ws()
    fs_no_test = {"connect_requested": None, "objects": ["Account"],
                 "account_fields": ["Account Name"], "contact_fields": None,
                 "inboxes": ["Support"], "test_contact_email": None}
    r3 = features.resolve_setup(FEATURE_ID, fs_no_test, connected)
    check("complete WITHOUT a test email -> still complete, no preview forced",
          r3["status"] == "complete" and r3["preview"] is None)

    fs_with_test = dict(fs_no_test, test_contact_email="jordan@acme.example")
    r4 = features.resolve_setup(FEATURE_ID, fs_with_test, connected)
    check("complete WITH a test email -> preview runs for real",
          r4["status"] == "complete" and r4["preview"]["status"] == "ok"
          and r4["preview"]["values_by_object"]["Account"]["Account Name"] == "Acme Corp")

    write_fs = {"connect_requested": None, "objects": ["Contact"],
               "contact_fields": ["Contact Name"], "account_fields": None,
               "inboxes": ["Support"], "test_contact_email": "jordan@acme.example"}
    r5 = features.resolve_setup(WRITE_FEATURE_ID, write_fs, connected)
    check("a write-kind feature never gets a preview — nothing exists to show yet",
          r5["status"] == "complete" and r5["preview"] is None)

    # ---- capability 7 for a WRITE feature: test_create() actually creates --
    # (the follow-up fix: withholding the nudge wasn't enough on its own —
    # a write feature needed a REAL way to prove itself, same as a view
    # feature's preview_feature() or a connector's real test-run.)
    check("create_contact() returns a real record with a fresh id",
          salesforce_mock.create_contact({"Name": "Jamie Doe"})["contact_id"]
          .startswith("created-"))

    write_feature = r5["feature"]
    tc1 = features.test_create(write_feature, {"Contact Name": "Jamie Doe"})
    check("test_create happy path: creates a real record via the mock, "
          "resolving the display label to Salesforce's own api field name",
          tc1["status"] == "ok" and tc1["object"] == "Contact"
          and tc1["record"]["name"] == "Jamie Doe"
          and tc1["record"]["contact_id"].startswith("created-"))

    tc2 = features.test_create(write_feature, {"Contact Name": "Jamie Doe",
                                               "Contact Email": "jamie@example.com"})
    check("test_create rejects a field the admin never chose to expose -- "
          "never silently drop it, never silently accept it",
          tc2["status"] == "error" and "Contact Email" in tc2["reason"])

    check("copilot.test_create_feature: unknown feature id is an error",
          copilot.test_create_feature({"id": "not_a_real_feature"}, {}, connected)
          ["status"] == "error")
    check("copilot.test_create_feature: a VIEW feature has nothing to create",
          copilot.test_create_feature({"id": FEATURE_ID}, {}, connected)
          ["status"] == "error")
    check("copilot.test_create_feature: re-checks prerequisites server-side, "
          "never trusting the client's belief that setup finished",
          copilot.test_create_feature(write_feature, {"Contact Name": "X"},
                                      connected_apps.load())["status"] == "error")
    tc3 = copilot.test_create_feature(write_feature, {"Contact Name": "Jamie Doe"}, connected)
    check("copilot.test_create_feature: happy path end to end",
          tc3["status"] == "ok" and tc3["record"]["name"] == "Jamie Doe")

    # ---- capability 4 generalizes past Salesforce: the SAME write flow, -----
    # driving a genuinely different app (ClickUp), config-only (task #10) --
    # ClickUp's write feature ALSO gets steps 5/6 (Prefill Fields, Quick
    # Access, 2026-08-26) that Salesforce's doesn't -- both optional, but
    # still asked once before "complete", so this no longer completes in
    # one call the way Salesforce's write feature does; see below.
    clickup_connected = _connected_ws("clickup")
    clickup_fs_base = {"connect_requested": None, "objects": ["Task"],
                       "task_fields": ["Title", "List"], "inboxes": ["Support"],
                       "test_contact_email": None}
    r7a = features.resolve_setup("clickup_create_task_from_hiver", clickup_fs_base,
                                 clickup_connected)
    check("ClickUp write feature: steps 1-4 done -> asks Prefill Fields next, "
          "not complete yet",
          r7a["status"] == "needs_info"
          and r7a["questions_structured"][0]["slot"] == "feature_setup.prefill_fields"
          and r7a["questions_structured"][0]["kind"] == "form")

    clickup_fs_prefill = {**clickup_fs_base, "prefill_requested": True,
                          "prefill_fields": [{"field": "List", "value": "Support Escalations"}]}
    r7b = features.resolve_setup("clickup_create_task_from_hiver", clickup_fs_prefill,
                                 clickup_connected)
    check("prefill values given -> moves on to the Quick Access question next",
          r7b["status"] == "needs_info"
          and r7b["questions_structured"][0]["slot"] == "feature_setup.quick_access_enabled")

    clickup_fs_skip_prefill = {**clickup_fs_base, "prefill_requested": False}
    r7c = features.resolve_setup("clickup_create_task_from_hiver", clickup_fs_skip_prefill,
                                 clickup_connected)
    check("declining prefill ('skip') still moves on to Quick Access, not stuck",
          r7c["status"] == "needs_info"
          and r7c["questions_structured"][0]["slot"] == "feature_setup.quick_access_enabled")

    clickup_fs = {**clickup_fs_prefill, "quick_access_enabled": True}
    r7 = features.resolve_setup("clickup_create_task_from_hiver", clickup_fs, clickup_connected)
    check("both optional steps answered -> completes, carrying prefill_fields "
          "and quick_access_enabled onto the feature",
          r7["status"] == "complete" and r7["preview"] is None
          and r7["feature"]["prefill_fields"] == {"List": "Support Escalations"}
          and r7["feature"]["quick_access_enabled"] is True)

    clickup_fs_all_skipped = {**clickup_fs_base, "prefill_requested": False,
                             "quick_access_enabled": False}
    r7d = features.resolve_setup("clickup_create_task_from_hiver", clickup_fs_all_skipped,
                                 clickup_connected)
    check("skipping BOTH optional steps still reaches complete, never blocked forever",
          r7d["status"] == "complete"
          and r7d["feature"]["prefill_fields"] == {}
          and r7d["feature"]["quick_access_enabled"] is False)

    salesforce_write_feature = r5["feature"]
    check("Salesforce's write feature never gets steps 5/6 -- scoped to "
          "ClickUp only for this pass",
          "prefill_fields" not in salesforce_write_feature
          or salesforce_write_feature.get("prefill_fields") == {})

    clickup_feature = r7["feature"]
    tc4 = features.test_create(clickup_feature,
                               {"Title": "Follow up", "List": "Support Escalations"})
    check("test_create dispatches to ClickUp's create_task via _CREATE_OPS, "
          "resolving display labels to clickup_mock's real kwargs",
          tc4["status"] == "ok" and tc4["object"] == "Task"
          and tc4["record"]["name"] == "Follow up"
          and tc4["record"]["list"] == "Support Escalations")

    tc5 = features.test_create(clickup_feature, {"Title": "Follow up", "Priority": "High"})
    check("test_create still rejects an unexposed field for a second app too",
          tc5["status"] == "error" and "Priority" in tc5["reason"])

    # ---- step 5's prefill defaults actually reach a manual create when the
    # agent leaves that field blank -- the whole point of "prefilling values
    # in the fields while creating tasks manually" (2026-08-26)
    tc7 = features.test_create(clickup_feature, {"Title": "Follow up"})
    check("List left blank -> falls back to its configured prefill default, "
          "never left empty when a default exists",
          tc7["status"] == "ok" and tc7["record"]["list"] == "Support Escalations")

    tc8 = features.test_create(clickup_feature, {"Title": "Follow up", "List": "Bugs"})
    check("an agent's own submitted value always overrides its prefill default",
          tc8["status"] == "ok" and tc8["record"]["list"] == "Bugs")

    tc6 = copilot.test_create_feature(
        clickup_feature, {"Title": "Follow up", "List": "Support Escalations"},
        clickup_connected)
    check("copilot.test_create_feature end to end for ClickUp",
          tc6["status"] == "ok" and tc6["record"]["name"] == "Follow up")

    # ---- rendering: TEST RUN line, or a real-conversation nudge when absent -
    draft_with_preview = copilot.render_feature(r4)
    check("draft shows the real test-run values, not just that setup finished",
          "TEST RUN" in draft_with_preview and "Acme Corp" in draft_with_preview)

    suggestion = copilot._test_conversation_suggestions()
    check("the nudge names REAL conversations (an @ address each), not placeholders",
          "@" in suggestion and "Try a real conversation" in suggestion)

    # ---- Track B: test_contact_email is offered as real conversations too ---
    sf_ws = _connected_ws()
    spec = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
            "condition_groups": [],
            "actions": [{"type": "connector", "recipe": RECIPE_ID,
                        "native_action_id": None, "target_name": None,
                        "title_hint": None, "test_contact_email": None,
                        "custom_plan": None}],
            "ai_extract": None, "unsupported_requests": [], "closing": False,
            "unmappable": []}
    r6 = validator.validate(spec, "assign to the csm", apps_ws=sf_ws)
    q = r6["questions_structured"][0]
    check("test_contact_email is asked as a CHOICE of real conversations, "
          "with a free-text fallback — not a bare open text box",
          q["slot"] == "actions[0].test_contact_email" and q.get("kind") == "choice"
          and q.get("allow_other") is True
          and all("@" in o["value"] for o in q["options"]))

    print(f"real conversation unit cases: {units - fails}/{units} passed")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
