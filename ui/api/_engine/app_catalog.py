"""THE single per-app object/field catalog every capability draws from —
Track A's view/write field pickers, Track B's dynamic-plan query engine and
assign/tag guardrails, and any future app's onboarding. One field,
described once, powers all of it.

Before this file, the SAME kind of information was described twice, in two
different shapes, with no shared source of truth: apps/schema.py's
FIELD_CATALOG (display names, for Track A's "which fields to show") and
salesforce_schema.py's OBJECTS (API field names + assignable/taggable
flags, for Track B's planner). Onboarding a second app would have meant
writing BOTH shapes by hand for it. Both those modules now DERIVE their
shape from this one (see field_catalog()/api_objects() below) so existing
behavior is provably unchanged — same labels, same standard/custom split,
same assignable/taggable sets — while there is now exactly one place to
add a new app's real objects/fields.

ONBOARDING A NEW APP means adding one entry to CATALOG below (its real
objects/fields) — nothing else in this file changes shape. What ELSE a new
app needs (auth prerequisites, native action blocks, a mock/real API
client) lives in its own genuinely separate concern: connected_apps.json
(auth), automation/schema.py's NATIVE_ACTIONS (native app-action
automations, capability 5), and a per-app service module registered in
automation/executor.py's APP_SERVICES (capability 6's query/describe ops).
This file is ONLY "what objects and fields does this app have."

Per-field flags — a deliberate claim about what's safe to do with a field,
never inferred from its data type alone:
  view       -- Track A can show this field (apps/setup.py's read step)
  write      -- Track A can let an admin FILL this field when CREATING a
                record (capability 4 — the write-usecase step)
  custom     -- true = a custom field; shown separately, never treated as
                less legitimate than a standard one
  assignable -- legal source for a connector's `assign` terminal
  taggable   -- legal source for a connector's `add_tag` terminal
Any flag not given on a field defaults to False — the safe default for
every one of these is "no", never "yes, probably fine."
"""

CATALOG = {
    "salesforce": {
        "Contact": {
            "table": "contacts",
            "fields": {
                # insertion order here is the order Track A's field-picker
                # OFFERS these — kept matching the pre-app_catalog.py order
                # exactly (name, email, phone, role) rather than the id/fk
                # fields' position, which don't show (view defaults False).
                "contact_id": {"label": "Contact ID", "type": "id"},
                "name": {"label": "Contact Name", "type": "string", "view": True, "write": True},
                "email": {"label": "Contact Email", "type": "email", "view": True},
                "account_id": {"label": "Account", "type": "id"},
                "phone": {"label": "Contact Phone", "type": "string", "view": True, "write": True},
                "role": {"label": "Contact Role", "type": "string", "view": True, "write": True},
                "preferred_language": {"label": "Preferred Language", "type": "string",
                                       "view": True, "write": True, "custom": True},
            },
        },
        "Account": {
            "table": "accounts",
            "fields": {
                "account_id": {"label": "Account ID", "type": "id"},
                "name": {"label": "Account Name", "type": "string", "view": True, "write": True},
                "website": {"label": "Account Website", "type": "string", "view": True, "write": True},
                "owner_email": {"label": "Account Owner", "type": "email", "view": True,
                                "assignable": True},
                "annual_revenue": {"label": "Annual Revenue", "type": "number",
                                   "view": True, "write": True},
                "number_of_employees": {"label": "Number of Employees", "type": "number",
                                        "view": True, "write": True},
                "phone": {"label": "Phone", "type": "string", "view": True, "write": True},
                "renewal_date": {"label": "Renewal Date", "type": "date", "view": True,
                                 "write": True, "custom": True},
                "health_score": {"label": "Health Score", "type": "number", "view": True,
                                 "custom": True},
            },
        },
        "AccountTeamMember": {
            "table": "account_team",
            "fields": {
                "account_id": {"label": "Account", "type": "id"},
                "user_id": {"label": "User ID", "type": "id"},
                "name": {"label": "Name", "type": "string", "view": True},
                "email": {"label": "Email", "type": "email", "view": True, "assignable": True},
                "role": {"label": "Role", "type": "string", "view": True},  # "CSM" | "AE"
            },
        },
        "Opportunity": {
            "table": "opportunities",
            "fields": {
                "opportunity_id": {"label": "Opportunity ID", "type": "id"},
                "account_id": {"label": "Account", "type": "id"},
                "name": {"label": "Opportunity Name", "type": "string", "view": True, "write": True},
                "stage": {"label": "Stage", "type": "string", "view": True, "write": True,
                         "taggable": True},
                "amount": {"label": "Amount", "type": "number", "view": True, "write": True},
                "owner_email": {"label": "Opportunity Owner", "type": "email", "view": True,
                                "assignable": True},
            },
        },
        "Case": {
            "table": "cases",
            "fields": {
                "case_id": {"label": "Case ID", "type": "id"},
                "account_id": {"label": "Account", "type": "id"},
                "subject": {"label": "Subject", "type": "string", "view": True, "write": True},
                "priority": {"label": "Priority", "type": "string", "view": True, "write": True,
                            "taggable": True},
                "status": {"label": "Status", "type": "string", "view": True, "write": True,
                          "taggable": True},
                "owner_email": {"label": "Case Owner", "type": "email", "view": True,
                                "assignable": True},
            },
        },
    },
    "clickup": {
        # WRITE only — capability 4's second app-agnostic proof (after
        # salesforce_create_contact): the same field-config step Track A
        # already had, now driving a genuinely different app. Field labels
        # are chosen to be human-facing; the underlying api names are
        # DELIBERATELY the exact kwargs clickup_mock.create_task() already
        # takes, so apps/setup.py's generic label->api_name resolution
        # (field_by_label) hands back a dict that op accepts directly —
        # no per-app adapter needed. No "view" flags anywhere: there is no
        # Track A view feature for ClickUp (yet), so nothing here claims one.
        "Task": {
            "table": "tasks",
            "fields": {
                "list_name": {"label": "List", "type": "string", "write": True},
                "title": {"label": "Title", "type": "string", "write": True},
                "description": {"label": "Description", "type": "string", "write": True},
                "assignee": {"label": "Assignee", "type": "string", "write": True},
                "due_date": {"label": "Due Date", "type": "string", "write": True},
                "priority": {"label": "Priority", "type": "string", "write": True},
            },
        },
    },
}


def objects_for(app):
    """Every object name onboarded for this app."""
    return sorted(CATALOG.get(app, {}))


def field_catalog(app):
    """apps/schema.py's FIELD_CATALOG shape: {object: {"standard": [...],
    "custom": [...]}} of display LABELS — Track A's view-field picker reads
    this, unchanged from before this file existed."""
    out = {}
    for obj, spec in CATALOG.get(app, {}).items():
        standard, custom = [], []
        for f in spec["fields"].values():
            if not f.get("view"):
                continue
            (custom if f.get("custom") else standard).append(f["label"])
        if standard or custom:
            out[obj] = {"standard": standard, "custom": custom}
    return out


def writable_field_catalog(app):
    """The capability-4 (write-usecase) analogue of field_catalog(): display
    LABELS for fields an admin can FILL when creating a record, standard vs
    custom, same shape."""
    out = {}
    for obj, spec in CATALOG.get(app, {}).items():
        standard, custom = [], []
        for f in spec["fields"].values():
            if not f.get("write"):
                continue
            (custom if f.get("custom") else standard).append(f["label"])
        if standard or custom:
            out[obj] = {"standard": standard, "custom": custom}
    return out


def api_objects(app):
    """salesforce_schema.py's OBJECTS shape: {object: {"table", "fields"
    (api_name -> type), "assignable_fields", "taggable_fields"}} — Track B's
    planner/query-engine/guardrail vocabulary, unchanged from before this
    file existed."""
    out = {}
    for obj, spec in CATALOG.get(app, {}).items():
        out[obj] = {
            "table": spec["table"],
            "fields": {name: f["type"] for name, f in spec["fields"].items()},
            "assignable_fields": [n for n, f in spec["fields"].items() if f.get("assignable")],
            "taggable_fields": [n for n, f in spec["fields"].items() if f.get("taggable")],
        }
    return out


def label_for(app, object_name, api_name):
    """The display label for one field — used wherever a plan or a query
    result needs to show a real name instead of an internal api key."""
    f = CATALOG.get(app, {}).get(object_name, {}).get("fields", {}).get(api_name)
    return f["label"] if f else api_name


def field_by_label(app, object_name):
    """label -> api field name for one object — the reverse of label_for(),
    used wherever a chosen DISPLAY field (what Track A's field-config step
    stores) needs to be resolved back to the fixture's real key to actually
    fetch a value for it (apps/setup.py's "test on a real conversation"
    preview)."""
    fields = CATALOG.get(app, {}).get(object_name, {}).get("fields", {})
    return {f["label"]: name for name, f in fields.items()}
