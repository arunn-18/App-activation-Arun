import os
"""v2 rule-spec schema: the legal vocabulary of Hiver automations.

Grounded in the 90-day prod dump (see ../eval/README.md): trigger names, condition
properties, operators, and action payloads are the real `automation_ai` DB vocabulary,
so a spec that validates here is buildable in prod.

Semantics: condition_groups are AND'd; conditions within a group are OR'd; a
condition's values array is any-of. (Assumed from data — pending eng confirmation.)
"""

TRIGGERS = {
    "new_conversation_inbound": "a new conversation arrives (started by the customer)",
    "new_conversation_outbound": "we start a new conversation (first email is ours)",
    "new_conversation": "any new conversation, inbound or outbound",
    "new_email_incoming_from_anyone": "any incoming email on an existing conversation",
    "new_email_incoming_from_contact": "the contact replies on an existing conversation",
    "new_email_outgoing": "we send an email",
    "conversation_moved_to_inbox": "a conversation is moved into this inbox",
}

# Builder-vocabulary labels — what admins actually see in Hiver's automation
# builder (rule-menu.md §2/§3, builder screenshots 2026-07-07; T3 confirmed by
# Mithil 2026-08-09). Users can only verify a rule in the vocabulary they know,
# so every user-facing surface renders THESE; internal ids stay in machine JSON.
# NOTE: keep TRIGGERS (id -> description) untouched — it feeds the extraction
# prompt, and changing it perturbs the model.
TRIGGER_LABELS = {
    "new_conversation_inbound": "New conversation (inbound) is received",
    "new_conversation_outbound": "New conversation (outbound) is sent",
    "new_conversation": "New conversation (inbound or outbound) is created",
    "conversation_moved_to_inbox": "Conversation is moved to this Shared Inbox",
    "new_email_incoming_from_anyone": "External reply is received from anyone",
    "new_email_incoming_from_contact": "External reply is received from the contact",
    "new_email_outgoing": "Mailbox reply is sent",
}

PROPERTY_LABELS = {
    "subject": "Subject",
    "body": "Body",
    "from": "From Email",
    "to": "To Email",
    "cc": "Cc",
    "bcc": "Bcc Email",
    "reply_to": "Reply-to Email",
    "from_domain": "From Domain",
    "to_domain": "To Domain",
    "reply_to_domain": "Reply-to Domain",
    "status": "Status",
    "tag": "Tags",
    "assignee": "Assignee",
    "day": "Day",
    "email_creation_time": "Creation Time",
    "date": "Date",
    "hours_passed_since": "Time Passed Since",
    "ai_variable": "AI Variable",
}

DISTRIBUTION_METHODS = ["round_robin", "load_balancing"]
STATUS_VALUES = ["open", "close", "pending"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

TEXT_OPS = ["contains", "is", "does not contain", "matches"]
ADDR_OPS = ["contains", "is", "does not contain", "is not", "matches"]

# AI extraction variables (the "AI step"): the model defines variables that Hiver's
# AI fills per conversation; conditions can gate on them, note bodies can embed them
# as {{name}}. Types and ops observed in the 90d prod dump (18 eval records).
AI_VARIABLE_TYPES = ["boolean", "text", "number", "date", "time", "email", "single_select"]
AI_VARIABLE_OPS = ["is", "is_any_of", "exists", "does_not_exist"]

# property -> allowed ops (+ optional fixed value set)
CONDITION_PROPERTIES = {
    "subject":      {"ops": TEXT_OPS, "kind": "text"},
    "body":         {"ops": TEXT_OPS, "kind": "text"},
    "from":         {"ops": ADDR_OPS, "kind": "address"},
    "to":           {"ops": ADDR_OPS, "kind": "address"},
    "cc":           {"ops": ADDR_OPS, "kind": "address"},
    "bcc":          {"ops": ADDR_OPS, "kind": "address"},
    "reply_to":     {"ops": ADDR_OPS, "kind": "address"},
    "from_domain":  {"ops": ADDR_OPS, "kind": "address"},
    "to_domain":    {"ops": ADDR_OPS, "kind": "address"},
    "reply_to_domain": {"ops": ADDR_OPS, "kind": "address"},
    "status":       {"ops": ["is", "is not"], "kind": "enum", "values": STATUS_VALUES},
    # entity conditions: the conversation's CURRENT tags/assignee. Builder-
    # confirmed (rule-menu §3.2); unavailable on new-conversation triggers,
    # where the conversation has no tags/assignee/status yet (see compat_error).
    "tag":          {"ops": ["is_any_of", "is_all_of", "is_none_of"],
                     "kind": "entity", "entity": "tag"},
    "assignee":     {"ops": ["is", "is not", "is_any_of", "is_none_of"],
                     "kind": "entity", "entity": "user"},
    "day":          {"ops": ["is_any_of"], "kind": "enum", "values": DAYS},
    "email_creation_time": {"ops": ["is_within", "is_outside_business_hours",
                                    "is_within_business_hours"], "kind": "time"},
    "date":         {"ops": ["is_between", "is_before", "is_after", "is_on"], "kind": "time"},
    "hours_passed_since": {"ops": ["no_email_outgoing", "no_status_change",
                                   "no_tag_change", "no_assignee_change"], "kind": "duration"},
    "ai_variable":  {"ops": AI_VARIABLE_OPS, "kind": "ai"},
}

# known-impossible trigger x property combos
# A conversation has no tags/assignee/status yet at the moment it arrives, so
# the builder does not offer those conditions on the New-conversation triggers
# (rule-menu §3.2 + the 2023 spec). They ARE available on reply and
# state-change triggers.
NEW_CONVERSATION_TRIGGERS = ("new_conversation_inbound", "new_conversation_outbound",
                             "new_conversation", "conversation_moved_to_inbox")
STATE_PROPERTIES = ("status", "tag", "assignee")


# ---- pilot scope -------------------------------------------------------
# The demo covers non-AI, non-integration automations. The AI surface stays in
# the engine (built and measured; it belongs to another team in production) but
# is DECLARED out of scope when serving, so the product never quietly does what
# its own footer says it won't. Off by default so the eval suites keep measuring
# the full capability; the servers turn it on.
PILOT_SCOPE = os.environ.get("COPILOT_PILOT_SCOPE", "0") == "1"

OUT_OF_SCOPE = {
    "ai": "AI detection or extraction",
    "time": "Time Passed Since / Date / Day conditions",
}
TIME_PROPERTIES = ("hours_passed_since", "date", "day", "email_creation_time")


def compat_error(trigger, prop):
    if prop in STATE_PROPERTIES and trigger in NEW_CONVERSATION_TRIGGERS:
        return (f"'{PROPERTY_LABELS.get(prop, prop)}' conditions aren't available on "
                f"new-conversation triggers — a conversation has no tags, assignee "
                f"or status yet when it first arrives. Use a reply trigger "
                f"(e.g. a follow-up on an existing conversation) instead")
    if prop == "hours_passed_since" and trigger not in (
            "new_email_outgoing", "new_conversation_outbound"):
        return ("'hours_passed_since' (waiting-for-reply timers) only works on outgoing "
                "triggers (new_email_outgoing / new_conversation_outbound)")
    return None

# ---------------------------------------------------------------------------
# Connector recipes ("Make an API call" / app-based automations, v2.8)
#
# A recipe is a named, ordered CHAIN of steps against one third-party app.
# Two step kinds today:
#   api_call — {kind, op, args (may contain {{var}} refs), extract_variables}
#              op names a function on that app's mock/real service; args are
#              template-filled from variables collected so far;
#              extract_variables pulls named fields out of the call's
#              response into the variable namespace for LATER steps.
#   assign   — {kind, target} terminal step; target is usually a {{var}} ref
#              resolved from an earlier api_call's extracted variables.
#
# GENERIC (this shape is the mechanism — keep it for recipe #2+): the dict
# shape (id -> app/name/description/chain/prerequisites), the extract_variables
# hand-off between steps, and the prerequisites list of boolean flags all
# generalize to any future app/recipe. Adding a recipe is a data entry here
# plus (if the app has no mock yet) a small mock service module — no engine
# code changes required. `list(RECIPES)` also drives the `recipe` enum on
# ACTIONS["connector"] below, so a new entry is automatically legal vocabulary
# for extraction and validation both.
#
# SHAPED BY HAVING SEEN ONLY ONE EXAMPLE (revisit once the golden dataset
# lands more recipes):
#   - every step is api_call or assign; a real recipe #2 might need a
#     terminal action that isn't `assign` (tag, note, status) or a step that
#     branches on the response — executor.py's chain runner only knows these
#     two kinds today.
#   - the CSM-vs-AE role filtering for this recipe happens INSIDE the mock
#     service's op (get_account_team_csm queries "the CSM", not "the team"),
#     not as generic chain logic — that keeps the executor simple, but it
#     means recipe #2 needing real branching logic has no home yet; decide
#     then whether that belongs in the chain shape or stays a mock-service
#     detail.
#   - prerequisites are plain boolean workspace-state flags. A recipe needing
#     a configured VALUE (e.g. "which Salesforce field maps to X") doesn't fit
#     this shape — don't stretch it; extend the prerequisite entry then.
RECIPES = {
    "salesforce_account_csm_autoassign": {
        "app": "salesforce",
        "name": "Auto-assign to the account's CSM (Salesforce)",
        "description": ("When a new conversation arrives, look up the sender's Salesforce "
                        "Account (via their Contact record) and assign the conversation to "
                        "that Account's CSM (Customer Success Manager) from the Account Team."),
        "chain": [
            {"kind": "api_call", "op": "find_contact_by_email",
             "args": {"email": "{{contact_email}}"},
             "extract_variables": {"account_id": "account_id", "contact_id": "contact_id"}},
            {"kind": "api_call", "op": "get_account_team_csm",
             "args": {"account_id": "{{account_id}}"},
             "extract_variables": {"csm_email": "email", "csm_name": "name"}},
            {"kind": "assign", "target": "{{csm_email}}"},
        ],
        "prerequisites": ["salesforce_connected", "account_team_enabled"],
    },
}

# prerequisite flag -> what it means, for error/status messages
PREREQUISITE_LABELS = {
    "salesforce_connected": "the Salesforce app must be connected",
    "account_team_enabled": "Salesforce Account Team must be enabled with a CSM role",
}

# prerequisite flag -> the one-click fix, when the flag can be satisfied by a
# real (mocked) connect action rather than just a static error. `phrase` is
# what a click composes into chat (connected_apps.connect() recognizes it via
# copilot's Track A wiring); not every prerequisite has one yet (e.g.
# account_team_enabled has no mock "enable Account Team" action -- it's
# assumed already configured on the Salesforce side).
PREREQUISITE_ACTIONS = {
    "salesforce_connected": {"label": "Connect Salesforce", "phrase": "connect salesforce"},
}

# action type -> param spec.
#   required:   must be non-empty before the rule is complete
#   provenance: every value must literally appear in the user's own messages
#   question:   what to ask when the param is missing
#   enum_labels: optional {value: human label} for choice-question rendering
#                (falls back to the raw enum value when absent)
ACTIONS = {
    "add_tag": {
        "params": {"tags": {"list": True, "required": True, "provenance": True, "entity": "tag",
                            "question": "Which tag(s) should I apply?"}}},
    "remove_tag": {
        "params": {"tags": {"list": True, "required": True, "provenance": True, "entity": "tag",
                            "question": "Which tag(s) should I remove?"}}},
    "assign": {
        "params": {"target": {"required": True, "provenance": True, "entity": "user",
                              "question": "Who should the conversation be assigned to?"}}},
    "assign_among": {
        "params": {"targets": {"list": True, "required": True, "provenance": True, "entity": "user", "min": 2,
                               "question": "Which people should I distribute between (need at least two)?"},
                   # the builder makes you choose; naming several people does not
                   # imply round robin, so ask instead of assuming
                   "distribution": {"required": True, "provenance": False,
                                    "enum": DISTRIBUTION_METHODS,
                                    # naming several people does NOT imply a
                                    # method; the user's words must support the
                                    # one chosen, else we ask (see validator)
                                    "provenance_enum": {
                                        "round_robin": ["round robin", "round-robin",
                                                        "in turn", "rotate", "taking turns",
                                                        "take turns", "alternate"],
                                        "load_balancing": ["load balanc", "fewest",
                                                           "least busy", "evenly",
                                                           "balance the load", "workload"],
                                    },
                                    "question": "How should it be shared out — round robin "
                                                "(strictly in turn) or load balancing (to "
                                                "whoever has the fewest open conversations)?"}}},
    "status": {
        "params": {"status_value": {"required": True, "provenance": False, "enum": STATUS_VALUES,
                                    "question": "Which status should I set — open, pending, or closed?"}}},
    "add_note": {
        "params": {"content": {"required": True, "provenance": False,
                               "question": "What should the note say?"},
                   "pinned": {"required": False}}},
    "send_mail": {
        "params": {"body_hint": {"required": True, "provenance": False,
                                 "question": "What should the auto-reply say (or which saved template should it use)?"}}},
    "send_notification": {
        "params": {"email_enabled": {"required": False}}},
    "add_to_sm": {
        "params": {"inbox": {"required": True, "provenance": True, "entity": "inbox",
                             "question": "Which shared inbox should the conversation be added to?"}}},
    "remove_from_sm": {
        "params": {"inbox": {"required": False}}},
    # Connector action: fires an app recipe's chain (see RECIPES above). Like
    # assign_among's distribution method, `recipe` is a structural choice the
    # user's ask must land on explicitly — the model maps intent to a recipe
    # id (extract.py routes on RECIPES' descriptions), but the id itself is
    # required vocabulary, never inferred/defaulted when more than one recipe
    # exists. With exactly one recipe today this rarely surfaces as a
    # question in practice, but the check is real and generalizes as-is.
    #
    # test_contact_email is this recipe's ONE setup-time slot — a real contact
    # address to test-run the chain against before the rule is marked done
    # (see copilot.connector_test_run). It is genuinely customer-supplied, so
    # it carries provenance like any other free-text value. Do NOT assume a
    # future recipe needs this same single-slot shape — a recipe with its own
    # config needs (see the RECIPES comment) needs its own param design; this
    # is only what recipe #1 happens to need.
    "connector": {
        "params": {"recipe": {"required": True, "provenance": False,
                              "enum": list(RECIPES),
                              "enum_labels": {rid: r["name"] for rid, r in RECIPES.items()},
                              "question": "Which app automation should this run?"},
                   "test_contact_email": {"required": True, "provenance": True,
                                          "question": "What's a real contact email address "
                                                      "I can use to test this end-to-end "
                                                      "before it's marked done?"}}},
}

# asks we recognize but don't build — name them, don't fake them
UNSUPPORTED = {
    "custom_field": "setting or reading custom fields",
    "custom_object": "custom-object lookups",
    "approval": "approval flows",
    "sla": "SLA policies (separate feature, not an automation)",
    # "connector" was removed from here in v2.8 — it is now a real, if
    # narrow, ACTIONS entry (see RECIPES above). This entry covers every
    # OTHER connector/integration ask, which still isn't buildable — named
    # honestly instead of silently dropped, exactly like the rest of this
    # dict. Do not fold recipe-matching asks in here.
    "connector_other": ("connector automations other than the one currently supported "
                        "recipe (Salesforce auto-assign to the account's CSM)"),
}

# quantifiers that count as an explicit "run on everything" statement;
# bare plurals ("incoming emails") deliberately do NOT count
ALL_MAIL_QUANTIFIERS = ["all ", "every ", "everything", "each ", "any email", "any conversation",
                        "any incoming", "todos", "alle "]


# ---------------------------------------------------------------------------
# Track A: "configure an existing App feature" — NOT an automation. No
# trigger, no conditions, no action chain; it's a one-time on/off (or
# one-time confirm) for a capability the app already has. Apps-panel-only —
# the Automations panel has no equivalent to route this onto, so it is
# deliberately NOT wired into ACTIONS/RECIPES above; see engine/features.py
# for why it gets its own small module instead of being forced through the
# rule-spec engine.
#
# GENERIC: the dict shape (id -> app/name/description/prerequisites) and the
# prerequisite-flag check reuse the same mechanism as RECIPES' prerequisites,
# on purpose — both ask the same question ("is this app connected and
# configured enough to use?"). Adding a Track A feature is a data entry here.
#
# SHAPED BY ONE EXAMPLE (updated 2026-08-18 against the real product spec —
# "Apps Activation Steps: Usecase-wise steps"): a Track A feature is now a
# real guided flow, not a single yes/no check:
#   1. Authentication      -- prerequisites, same mechanism as RECIPES'
#   2. Record-level visibility config -- pick which objects to show
#      (object_choices below), from the platform-wide out-of-the-box list
#      (ALL_SUPPORTED_OBJECTS)
#   3. Field config - Read -- for each chosen object, pick fields from a
#      live "describe" call (FIELD_CATALOG / salesforce_mock.describe_fields)
#      -- standard AND custom, proving the field list comes from an API call
#      rather than a hardcoded guess
#   4. Confirm & enable
# See engine/features.py's resolve_setup() for the question-planning that
# walks these in order, one blocking question at a time (mirrors
# validator.py's discipline).
#
# STILL SHAPED BY ONE EXAMPLE: only Account/Contact have a FIELD_CATALOG
# entry (this feature's own object_choices), and Field config - Write /
# Prefill fields / Quick Access (the product spec's other listed steps)
# are explicitly NOT built — they belong to "Managing CRM Records from
# Hiver", a use case out of scope for this pass. Don't stretch this feature
# to cover them.
FEATURES = {
    "salesforce_account_contact_details": {
        "app": "salesforce",
        "name": "View account & contact details",
        "description": ("Show the sender's Salesforce Account and Contact details "
                        "(company, owner, CSM, open cases) alongside the conversation."),
        "prerequisites": ["salesforce_connected"],
        "object_choices": ["Account", "Contact"],
    },
}

# The full out-of-the-box object list Salesforce's "Record-level visibility
# config" step can offer, per the product spec — kept here for the NEXT
# Track A feature (e.g. "Managing CRM Records from Hiver" would offer
# Opportunity/Lead/Case too); only Account/Contact are wired to a
# FIELD_CATALOG entry today, so only those are usable end to end.
ALL_SUPPORTED_OBJECTS = ["Account", "Contact", "Opportunity", "Lead", "Case"]

# Track A's "Field config - Read" step calls this catalog the way a real
# integration would call Salesforce's object-describe API — standard AND
# custom fields, so field selection is never a fixed hardcoded list. Only
# Account/Contact are populated (the one feature that needs them); adding a
# feature that uses Opportunity/Lead/Case needs their real field names
# supplied the same way these were, not invented.
FIELD_CATALOG = {
    "Account": {
        "standard": ["Account Name", "Account Website", "Account Owner",
                     "Annual Revenue", "Number of Employees", "Phone"],
        "custom": ["Renewal Date", "Health Score"],
    },
    "Contact": {
        "standard": ["Contact Name", "Contact Email", "Contact Phone", "Contact Role"],
        "custom": ["Preferred Language"],
    },
}
