"""The Salesforce CRM object model: objects, their fields, and which fields
are legal sources for a connector's TERMINAL action — the closed vocabulary
BOTH the mock service's generic query/describe ops (salesforce_mock.py) and
the dynamic connector planner (automation/planner.py) use. Lives at the top
level, shared infra like salesforce_mock.py/connected_apps.py, not owned by
either track.

This is the guardrail boundary for dynamic connector composition: a
model-proposed plan (automation/planner.py) may reference ONLY the objects
and fields declared here — nothing else exists as far as the planner or
plan_validator.py are concerned, however plausible a made-up field name
sounds. A hand-vetted RECIPES entry (automation/schema.py) doesn't need
this catalog at all (its chain is fixed, already proven); this catalog only
matters for a plan nobody has hand-verified yet.

`assignable_fields` / `taggable_fields`: which fields on an object are legal
SOURCES for a connector's terminal action (assign / add_tag respectively).
This is deliberately narrow — e.g. Case.Subject is real data but is NOT a
legal assign target (it's not an email), and Account.Name is real but NOT a
legal tag value (there is no such tag in the workspace). Marking a field
here is a claim that its VALUE genuinely makes sense as that action's
argument in the mock data, not just that the field exists.
"""

OBJECTS = {
    "Contact": {
        "table": "contacts",
        "fields": {"contact_id": "id", "email": "email", "account_id": "id"},
        "assignable_fields": [],
        "taggable_fields": [],
    },
    "Account": {
        "table": "accounts",
        "fields": {"account_id": "id", "name": "string", "owner_email": "email"},
        "assignable_fields": ["owner_email"],
        "taggable_fields": [],
    },
    "AccountTeamMember": {
        "table": "account_team",
        "fields": {"account_id": "id", "user_id": "id", "name": "string",
                   "email": "email", "role": "string"},  # role in {"CSM", "AE"}
        "assignable_fields": ["email"],
        "taggable_fields": [],
    },
    "Opportunity": {
        "table": "opportunities",
        "fields": {"opportunity_id": "id", "account_id": "id", "name": "string",
                   "stage": "string", "amount": "number", "owner_email": "email"},
        "assignable_fields": ["owner_email"],
        "taggable_fields": ["stage"],
    },
    "Case": {
        "table": "cases",
        "fields": {"case_id": "id", "account_id": "id", "subject": "string",
                   "priority": "string", "status": "string", "owner_email": "email"},
        "assignable_fields": ["owner_email"],
        "taggable_fields": ["priority", "status"],
    },
}
