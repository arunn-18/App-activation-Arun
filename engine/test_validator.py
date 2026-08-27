"""Validator/schema self-test: the failure modes this engine exists to kill
(VIP hallucination, missing tag, unnamed scope, illegal combos, unsupported
asks). automation/validator.py is shared machinery — every app automation
still needs its trigger/conditions/entity-resolution/provenance checked the
same way a generic rule would, copilot.py's own "needs an app action" gate
(see test_app_scope.py) sits on TOP of this, not instead of it.

App Activation only (2026-08-27 cleanup): this file used to also run a
"schema coverage" pass against eval/real-world-eval-set.jsonl (105 pure-Hiver
prod records with no app action in them at all) to prove the schema covered
real prod rules generically. That eval set moved to legacy/eval/ along with
the rest of the pre-Apps-Activation material (see legacy/README.md) — this
file's job now is proving the SHARED mechanics below are correct, not
re-validating an eval set this engine no longer targets.

Run: python3 test_validator.py
"""
import sys

from automation import validator
import workspace as wsmod


def run():
    fails = 0
    units = 0

    def check(name, cond):
        nonlocal fails, units
        units += 1
        if not cond:
            fails += 1
            print(f"UNIT FAIL: {name}")

    convo = "apply tag when conversation comes / only emails from acme.com"
    vip = {"trigger": "new_conversation_inbound", "scope_confirmed": False,
           "condition_groups": [[{"property": "from_domain", "op": "is", "values": ["acme.com"]}]],
           "actions": [{"type": "add_tag", "tags": ["VIP"]}]}
    res = validator.validate(vip, convo)
    check("VIP hallucination caught", res["hallucinated"]
          and res["hallucinated"][0]["value"] == "VIP")
    check("VIP -> asks for tag", any("tag" in q.lower() for q in res["questions"]))
    spec2 = validator.scrub(vip, res)
    check("VIP scrubbed from draft", spec2["actions"][0]["tags"] == [])

    res = validator.validate({"trigger": "new_conversation_inbound", "scope_confirmed": False,
                              "condition_groups": [], "actions": [{"type": "add_tag", "tags": []}]},
                             "apply tag when conversation comes")
    check("missing tag asked", any("tag" in q.lower() for q in res["questions"]))
    check("scope is an assumption, not a question",
          not any("every" in q.lower() for q in res["questions"])
          and any(a["slot"] == "scope" for a in res["assumptions"]))
    check("needs_info", res["status"] == "needs_info")

    # scope alone never blocks: trigger + action, no conditions -> complete
    # with the assumption carried on the result
    res = validator.validate({"trigger": "new_conversation_inbound",
                              "scope_confirmed": False, "condition_groups": [],
                              "actions": [{"type": "assign", "target": "jade"}]},
                             "route emails to jade")
    check("assumption completes the rule", res["status"] == "complete")
    check("assumption is disclosed", res["assumptions"]
          and res["assumptions"][0]["assumed"] == "everything")

    # an explicit everything-statement means scope is SPECIFIED, no assumption
    res = validator.validate({"trigger": "new_conversation_inbound",
                              "scope_confirmed": True, "condition_groups": [],
                              "actions": [{"type": "assign", "target": "jade"}]},
                             "assign everything to jade")
    check("confirmed scope carries no assumption", not res["assumptions"])

    res = validator.validate({"trigger": "new_conversation_inbound", "scope_confirmed": True,
                              "condition_groups": [[{"property": "hours_passed_since",
                                                     "op": "no_email_outgoing", "values": ["48:00"]}]],
                              "actions": [{"type": "send_notification"}]}, "x")
    check("incompatible trigger x hours_passed_since", res["status"] == "invalid")

    res = validator.validate({"trigger": "new_conversation_inbound", "scope_confirmed": True,
                              "condition_groups": [[{"property": "subject", "op": "contains",
                                                     "values": ["invoice"]}]],
                              "actions": [{"type": "custom_field"}],
                              "unsupported_requests": []},
                             "when subject has invoice set the priority custom field")
    check("unsupported called out", res["unsupported"])

    res = validator.validate({"trigger": "new_conversation_inbound", "scope_confirmed": False,
                              "condition_groups": [[{"property": "from", "op": "contains",
                                                     "values": ["specific senders"]}]],
                              "actions": [{"type": "status", "status_value": "close"}]},
                             "close mail from specific senders")
    check("meta-language value rejected", res["hallucinated"]
          and res["hallucinated"][0]["value"] == "specific senders")

    # ---- scope pin: an answered "run it on everything" beats conditions
    # re-derived from earlier messages (the Jade regression)
    jade_msgs = ["we get a lot of emails meant for jade, can you route them to her?",
                 "run it on every matching conversation"]
    jade = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
            "condition_groups": [[{"property": "to", "op": "contains",
                                   "values": ["jade"]}]],
            "actions": [{"type": "assign", "target": "jade"}]}
    res = validator.validate(jade, "\n".join(jade_msgs), user_messages=jade_msgs)
    check("scope pin fires", res.get("scope_pinned"))
    check("scope pin completes the rule", res["status"] == "complete")
    check("scope pin disclosed", any("dropped a condition" in n
                                     for n in res["entity_notes"]))
    spec2 = validator.scrub(jade, res)
    check("scope pin scrubs conditions", spec2["condition_groups"] == []
          and spec2["scope_confirmed"] is True)

    # a condition the user introduces AFTER the everything-answer supersedes it
    late_msgs = jade_msgs + ["actually, only emails sent to jade@brightpath.example"]
    late = {"trigger": "new_conversation_inbound", "scope_confirmed": False,
            "condition_groups": [[{"property": "to", "op": "contains",
                                   "values": ["jade@brightpath.example"]}]],
            "actions": [{"type": "assign", "target": "jade"}]}
    res = validator.validate(late, "\n".join(late_msgs), user_messages=late_msgs)
    check("later subset supersedes the pin", not res.get("scope_pinned"))
    check("later subset keeps its condition", late["condition_groups"])

    # "every" inside an ordinary sentence is not an everything-answer
    one_msgs = ["tag every new email from acme.com as VIP"]
    one = {"trigger": "new_conversation_inbound", "scope_confirmed": False,
           "condition_groups": [[{"property": "from", "op": "contains",
                                  "values": ["acme.com"]}]],
           "actions": [{"type": "add_tag", "tags": ["VIP"]}]}
    res = validator.validate(one, "\n".join(one_msgs), user_messages=one_msgs)
    check("plain sentence never pins", not res.get("scope_pinned"))

    # ---- COVERAGE: two problems on ONE slot must both be asked (the observed
    # regression: "assign to dara, john, sara" silently dropped john)
    ws_fix = wsmod.load()
    convo = "assign new incoming emails to dara, john and sara"
    spec = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
            "condition_groups": [],
            "actions": [{"type": "assign_among",
                         "targets": ["dara", "John Doe", "John Baker", "Sarah Lee"]}]}
    res = validator.validate(spec, convo, ws_fix)
    qs = " | ".join(res["questions"]).lower()
    check("coverage: unknown name asked", "dara" in qs)
    check("coverage: ambiguous name also asked (same slot)", "john" in qs)
    check("coverage: ambiguity quotes the USER's word, not the model's pick",
          "'john' matches more than one" in " | ".join(res["questions"]))
    check("coverage: two Johns collapse to ONE question",
          sum(1 for q in res["questions"] if "matches more than one" in q) == 1)
    # nothing scrubbed may vanish without a question or a note
    covered = {m["slot"] for m in res["missing"]}
    check("coverage: every scrubbed value is accounted for",
          all(h["slot"] in covered for h in res["hallucinated"])
          or res["entity_notes"])

    # ---- unmappable: declared, never approximated
    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [], "actions": [{"type": "add_tag", "tags": ["Urgent"]}],
         "enabled_inboxes": ["Support"],
         "unmappable": [{"request": "an existing tag VIP",
                         "why": "no condition property for tags"}]},
        "tag urgent when it already has tag VIP", ws_fix)
    check("unmappable surfaces on the result",
          res["unmappable"] and res["unmappable"][0]["request"] == "an existing tag VIP")
    check("unmappable does not block a buildable rule", res["status"] == "complete")

    # ---- docent: capability answers come from schema, keyed by topic
    import docent
    a = docent.answer("assignment options")
    check("docent: assignment names all three moves",
          "share among" in a and "unassign" in a and "one teammate" in a)
    check("docent: assignment names both distribution methods",
          "round robin" in a and "load balancing" in a)
    a = docent.answer("salesforce integration")
    check("docent: unsupported list is honest", "Salesforce" in a and "SLA" in a)
    a = docent.answer("what triggers exist")
    check("docent: triggers from schema labels",
          "New conversation (inbound) is received" in a)
    check("docent: unknown topic gets the overview",
          docent.answer("quantum entanglement") == docent.answer(""))

    # ---- docent keyword matching is word-boundary-aware, not naive substring
    # (2026-08-27 live review): "ai" inside "explain"/"maintain", "tag" inside
    # "advantage", "move" inside "remove", "api" inside "capital" must NOT
    # spuriously match a short topic keyword -- a real live bug, not a
    # hypothetical one (a meta-question containing "explain" was routed to
    # the AI-variables topic purely because "ai" is a substring of "explain").
    overview = docent.answer("")
    check("'explain' does not spuriously match the 'ai' keyword",
          docent.answer("will you suggest features if I explain my workflow")
          == overview)
    check("'advantage' does not spuriously match the 'tag' keyword",
          docent.answer("what's the advantage of this approach") == overview)
    check("'remove' does not spuriously match the 'move' keyword",
          docent.answer("can you remove duplicates") == overview)
    check("'capital' does not spuriously match the 'api' keyword",
          docent.answer("what's the capital investment needed") == overview)
    check("a genuine whole-word 'ai' still matches the AI-variables topic",
          "AI variables" in docent.answer("what can AI detect"))
    check("a genuine whole-word 'tag' still matches the tags topic",
          "Tags work two ways" in docent.answer("how do tags work"))

    # ---- docent.relevant_capabilities(): the structured sibling of answer()
    b = docent.relevant_capabilities("clickup integration")
    check("relevant_capabilities scoped to ClickUp names only ClickUp entries",
          b and all(x["app"] == "clickup" for x in b)
          and any(x["id"] == "clickup_create_task_from_hiver" and x["kind"] == "app_feature"
                  for x in b)
          and any(x["id"] == "clickup_create_task" and x["kind"] == "native_action" for x in b))
    b2 = docent.relevant_capabilities("salesforce integration")
    check("relevant_capabilities scoped to Salesforce names only Salesforce entries, "
          "including the recipe",
          b2 and all(x["app"] == "salesforce" for x in b2)
          and any(x["kind"] == "recipe" for x in b2))
    b3 = docent.relevant_capabilities("what integrations do you support")
    check("no app named -> every app's entries, same scope answer()'s own text covers",
          {x["app"] for x in b3} == {"salesforce", "clickup"})
    check("a non-integration topic has no discrete capability to badge -- "
          "empty, not invented",
          docent.relevant_capabilities("assignment options") == []
          and docent.relevant_capabilities("what triggers exist") == [])
    check("no topic at all -> no badges",
          docent.relevant_capabilities(None) == [] and docent.relevant_capabilities("") == [])

    # ---- preview dry-run: deterministic matcher over the mailbox fixture
    import preview as pv
    box = pv.load_mailbox()
    r = pv.preview({"trigger": "new_conversation_inbound",
                    "condition_groups": [], "actions": []}, box)
    check("preview: everything = whole pool", r["previewable"]
          and r["matched"] == r["total"] > 0)
    r = pv.preview({"trigger": "new_conversation_inbound", "condition_groups":
                    [[{"property": "from", "op": "contains",
                       "values": ["notifications@streamliner.example"]}]],
                    "actions": []}, box)
    check("preview: streamliner subset", r["previewable"]
          and 0 < r["matched"] < r["total"] and len(r["sample"]) == 3)
    r = pv.preview({"trigger": "new_conversation_inbound", "condition_groups":
                    [[{"property": "from_domain", "op": "is", "values": ["acme.com"]}],
                     [{"property": "subject", "op": "contains", "values": ["invoice"]}]],
                    "actions": []}, box)
    check("preview: AND-of-OR narrows", r["previewable"] and 0 < r["matched"] < 15)
    r = pv.preview({"trigger": "new_conversation_inbound", "condition_groups":
                    [[{"property": "ai_variable", "op": "is", "values": ["true"],
                       "variable": "x"}]], "actions": []}, box)
    check("preview: AI rule honestly unavailable", not r["previewable"])
    r = pv.preview({"trigger": "conversation_moved_to_inbox",
                    "condition_groups": [], "actions": []}, box)
    check("preview: moved trigger honestly unavailable", not r["previewable"])
    r = pv.preview({"trigger": "new_conversation_inbound", "condition_groups":
                    [[{"property": "from", "op": "does not contain",
                       "values": ["notifications@streamliner.example"]}]],
                    "actions": []}, box)
    check("preview: negative op is complement",
          r["matched"] == r["total"] - 14)

    # AI-gated rules are exempt: gates are deliberate structure, not scope noise
    ai_msgs = ["use AI to spot refund requests and tag them",
               "run it on every matching conversation"]
    ai = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
          "ai_extract": {"variables": [{"name": "refund_request", "type": "boolean",
                                        "description": "is this a refund request"}]},
          "condition_groups": [[{"property": "ai_variable", "op": "is",
                                 "variable": "refund_request", "values": ["true"]}]],
          "actions": [{"type": "add_tag", "tags": ["refund"]}]}
    res = validator.validate(ai, "\n".join(ai_msgs), user_messages=ai_msgs)
    check("AI gates never pinned away", not res.get("scope_pinned"))

    res = validator.validate({"trigger": None, "scope_confirmed": False,
                              "condition_groups": [], "actions": []}, "help me automate")
    check("empty spec asks trigger first", res["questions"]
          and res["questions"][0] == validator.TRIGGER_QUESTION)
    check("max 3 questions", len(res["questions"]) <= 3)

    # ---- AI extraction cases
    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [[{"property": "ai_variable", "op": "is",
                                "values": ["true"], "variable": "is_billing"}]],
         "actions": [{"type": "status", "status_value": "close"}],
         "ai_extract": None},
        "use ai to close billing emails")
    check("undeclared AI variable is an error", res["status"] == "invalid"
          and any("undeclared" in e for e in res["errors"]))

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [],
         "actions": [{"type": "add_note", "content": "urgency: {{urgency}}"}],
         "ai_extract": {"variables": [{"name": "urgency", "type": "single_select",
                                       "description": "urgency label", "options": []}]}},
        "have ai label urgency and note it")
    check("single_select without options asks", res["status"] == "needs_info"
          and any("possible values" in q for q in res["questions"]))

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [],
         "actions": [{"type": "add_note", "content": "summary: {{email_summary}}"}],
         "ai_extract": {"variables": [{"name": "is_billing", "type": "boolean",
                                       "description": "billing?", "options": []}]}},
        "note an ai summary of billing emails")
    check("note ref to undefined variable is an error", res["status"] == "invalid"
          and any("undefined AI variable" in e for e in res["errors"]))

    spec_opt = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
                "condition_groups": [],
                "actions": [{"type": "add_note", "content": "level: {{level}}"}],
                "ai_extract": {"variables": [{"name": "level", "type": "single_select",
                                              "description": "urgency",
                                              "options": ["critical", "wumpus"]}]}}
    res = validator.validate(spec_opt, "have ai label urgency critical or low, note the level")
    check("invented option label caught", any(h["value"] == "wumpus"
                                              for h in res["hallucinated"]))
    spec_opt = validator.scrub(spec_opt, res)
    check("invented option scrubbed",
          spec_opt["ai_extract"]["variables"][0]["options"] == ["critical"])

    # ---- entity validation (workspace fixture)
    ws = wsmod.load()

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [], "actions": [{"type": "assign", "target": "john"}]},
        "assign every new email to john", ws=ws)
    check("ambiguous John asks, never chooses", res["status"] == "needs_info"
          and any("more than one" in q for q in res["questions"]))

    spec_s = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
              "condition_groups": [], "actions": [{"type": "assign", "target": "sarah"}],
              "enabled_inboxes": ["Support"]}
    res = validator.validate(spec_s, "assign every new email to sarah", ws=ws)
    check("unique fuzzy resolves without asking", res["status"] == "complete"
          and res["resolutions"]
          and res["resolutions"][0]["canonical"] == "Sarah Lee")
    spec_s = validator.apply_resolutions(spec_s, res)
    check("resolution applied to spec", spec_s["actions"][0]["target"] == "Sarah Lee")

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [], "actions": [{"type": "assign", "target": "Sarah Lee"}],
         "enabled_inboxes": ["Support"]},
        "assign every new email to sarah", ws=ws)
    check("model's tool resolution re-verified from user's words",
          res["status"] == "complete" and not res["hallucinated"])

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [], "actions": [{"type": "assign", "target": "Dana Whitfield"}]},
        "assign every new billing email to sarah", ws=ws)
    check("workspace entity the user never referred to is still hallucinated",
          any(h["value"] == "Dana Whitfield" for h in res["hallucinated"]))

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [], "actions": [{"type": "add_tag", "tags": ["gold-partner"]}],
         "enabled_inboxes": ["Support"]},
        "tag all new emails gold-partner", ws=ws)
    check("unknown tag builds with create-first note", res["status"] == "complete"
          and res["entity_notes"])

    spec_t = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
              "condition_groups": [], "actions": [{"type": "add_tag", "tags": ["vip"]}]}
    res = validator.validate(spec_t, "tag all new emails vip", ws=ws)
    spec_t = validator.apply_resolutions(spec_t, res)
    check("tag casing canonicalized to workspace form",
          spec_t["actions"][0]["tags"] == ["VIP"])

    # ---- enabled_inboxes: EVERY automation needs this once a workspace is
    # loaded — a rule doesn't run workspace-wide any more than a Track A
    # feature does (that step's own precedent). Skipped entirely with no
    # workspace (the 56/56 core eval records above never set this and still
    # reach "complete", proving the ws=None skip already holds).
    otherwise_complete = {"trigger": "new_conversation_inbound", "scope_confirmed": True,
                          "condition_groups": [], "actions": [{"type": "add_tag", "tags": ["VIP"]}]}
    res = validator.validate(otherwise_complete, "tag urgent emails VIP", ws=ws)
    check("missing enabled_inboxes blocks completion once a workspace is loaded",
          res["status"] == "needs_info")
    inbox_q = next(q for q in res["questions_structured"] if q["slot"] == "enabled_inboxes")
    check("the inbox question is an actual multi-select of REAL workspace inboxes",
          inbox_q["kind"] == "choice" and inbox_q["multiple"] is True
          and {o["value"] for o in inbox_q["options"]} == {"Support", "Billing", "Events"})

    with_inboxes = {**otherwise_complete, "enabled_inboxes": ["Support", "Billing"]}
    res = validator.validate(with_inboxes, "tag urgent emails VIP", ws=ws)
    check("naming inbox(es) clears the gate -- otherwise-complete rule finishes",
          res["status"] == "complete")

    res = validator.validate(otherwise_complete, "tag urgent emails VIP", ws=None)
    check("no workspace context -> enabled_inboxes not required at all",
          res["status"] == "complete")

    # ---- coherence: contradictions and conflicting actions
    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [
             [{"property": "from", "op": "contains", "values": ["invoice@acme.com"]}],
             [{"property": "from", "op": "contains", "values": ["billing@acme.com"]}]],
         "actions": [{"type": "add_tag", "tags": ["Billing"]}]},
        "from invoice@acme.com tag Billing. also billing@acme.com")
    check("unsatisfiable AND on From asks two-automations", res["status"] == "needs_info"
          and any("never fire" in q for q in res["questions"]))

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [
             [{"property": "from", "op": "contains", "values": ["acme.com"]}],
             [{"property": "from", "op": "contains", "values": ["invoice@acme.com"]}]],
         "actions": [{"type": "status", "status_value": "close"}]},
        "close mail from acme.com, specifically invoice@acme.com")
    check("nested From values are NOT flagged",
          not any("never fire" in q for q in res["questions"]))

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [
             [{"property": "from", "op": "contains", "values": ["invoice@acme.com"]}]],
         "actions": [{"type": "assign", "target": "Dana"},
                     {"type": "assign", "target": "Sarah"}]},
        "from invoice@acme.com assign to Dana and also assign to Sarah")
    check("double assign asks how to resolve", res["status"] == "needs_info"
          and any("only the last one sticks" in q for q in res["questions"]))

    # ---- did-you-mean on near-miss entities (typo flows)
    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [],
         "actions": [{"type": "add_tag", "tags": ["Urgent"]}]},
        "tag every new email urgnet", ws=ws)  # model normalized the typo
    sq = res["questions_structured"]
    check("scrubbed typo offers did-you-mean choice",
          any(q.get("kind") == "choice"
              and any(o["value"] == "Urgent" for o in q["options"]) for q in sq))

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [],
         "actions": [{"type": "add_tag", "tags": ["urgnet"]}]},
        "tag every new email urgnet", ws=ws)  # model kept the typo verbatim
    check("verbatim typo tag offers did-you-mean, not create-first",
          any("did you mean" in q for q in res["questions"])
          and not res["entity_notes"])

    res = validator.validate(
        {"trigger": "new_conversation_inbound", "scope_confirmed": True,
         "condition_groups": [],
         "actions": [{"type": "add_tag", "tags": ["gold-partner"]}],
         "enabled_inboxes": ["Support"]},
        "tag all new emails gold-partner", ws=ws)
    check("unknown tag with no near-miss keeps create-first note",
          res["status"] == "complete" and res["entity_notes"])

    total_units = units
    print(f"unit cases: {total_units - (fails if fails <= total_units else total_units)}"
          f"/{total_units} passed" if fails == 0 else f"unit cases: {fails} FAILURES above")
    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return fails == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
