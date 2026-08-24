"""Track A schema: "configure an existing App feature" — a genuine peer of
automation/schema.py, not an appendage of it. No trigger, no conditions, no
action chain; enabling a feature is a one-time guided setup (see
apps/setup.py's resolve_setup()), never something that fires per
conversation. This is the whole reason Track A got split into its OWN
package (2026-08-18): its vocabulary (features, records, fields) has no
automation-schema equivalent, and squeezing it into automation/schema.py's
ACTIONS dict — or even bolting extra fields onto automation/extract.py's
output — kept producing exactly the "still works with the automation
schema" bug this split fixes. router.py decides which schema/extractor a
turn even needs BEFORE either one is loaded.

GENERIC: the FEATURES dict shape (id -> app/name/description/prerequisites/
object_choices/kind) generalizes to any future app/feature — see
apps/setup.py's resolve_setup() for the step order that walks them.
FIELD_CATALOG / WRITABLE_FIELD_CATALOG are DERIVED from app_catalog.py, the
one shared per-app object/field catalog Track B's planner also reads — not
owned or duplicated here; see app_catalog.py's own docstring for why.

`kind`: "view" (default — read-only Field config, apps/setup.py's existing
step 3) or "write" (capability 4 — Field config for creating a NEW record,
reading WRITABLE_FIELD_CATALOG instead of FIELD_CATALOG, a genuinely
separate branch in resolve_setup() that the view kind's steps never touch).

SHAPED BY HAVING SEEN THREE REAL USE CASES (per the 2026-08-18 product spec,
"Apps Activation Steps: Usecase-wise steps" — a CSV listing every Salesforce
use case and its setup steps): two features are built —
salesforce_account_contact_details ("Viewing account & contact details")
and salesforce_create_contact ("Managing CRM Records from Hiver"'s
create-a-Contact slice, kind="write"). The THIRD use case in the same spec
("Smart routing to right owner / auto-assignment") is Track B — it's an
automation with a trigger, so it lives in automation/schema.py's RECIPES,
not here. Prefill fields and Syncing Hiver conversations with SF records
(also in the same spec) are explicitly NOT built — they need steps this
module doesn't implement; don't stretch FEATURES to fake them.
"""
import app_catalog

FEATURES = {
    "salesforce_account_contact_details": {
        "app": "salesforce",
        "kind": "view",
        "name": "View account & contact details",
        "description": ("Show the sender's Salesforce Account and Contact details "
                        "(company, owner, CSM, open cases) alongside the conversation."),
        "prerequisites": ["salesforce_connected"],
        "object_choices": ["Account", "Contact"],
        # Apps Activation PRD (2026-08-24)'s Knowledge layer wants "example
        # phrasings" per catalogue entry — real asks this feature actually
        # matches, reused by docent.py's capability answers (never invented
        # fresh there) so an admin asking "what can this do?" sees something
        # they could actually type, not a restated description.
        "example_phrasings": ["set up Salesforce account cards for my shared mailbox",
                              "show me the customer's Salesforce account and contact info"],
    },
    "salesforce_create_contact": {
        "app": "salesforce",
        "kind": "write",
        "name": "Create a Contact from Hiver",
        "description": ("Let agents create a new Salesforce Contact directly from a "
                        "conversation, filling in the fields you choose here."),
        "prerequisites": ["salesforce_connected"],
        "object_choices": ["Contact"],
        "example_phrasings": ["let agents create a Salesforce Contact from a conversation",
                              "create a Contact from Hiver"],
    },
    "clickup_create_task_from_hiver": {
        "app": "clickup",
        "kind": "write",
        "name": "Create a Task from Hiver",
        # Deliberately a different id from automation/schema.py's
        # NATIVE_ACTIONS["clickup_create_task"] — this is Track A (an agent
        # manually creates one task, once, from an open conversation);
        # that other one is Track B (an automation fires it on a trigger,
        # no human in the loop). Same app, same underlying clickup_mock.py
        # call, two structurally separate mechanisms per the split this
        # engine has kept since Track A/B were divided.
        "description": ("Let agents create a new ClickUp task directly from a "
                        "conversation, filling in the fields you choose here."),
        "prerequisites": ["clickup_connected"],
        "object_choices": ["Task"],
        "example_phrasings": ["let agents create a ClickUp task directly from a conversation",
                              "Create a Task from Hiver"],
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
# custom fields, so field selection is never a fixed hardcoded list.
# DERIVED from app_catalog.py (the one shared source both this and Track
# B's planner read) — not hand-maintained here, so the two tracks can never
# describe the same field two different ways. Only Account/Contact end up
# populated (the one feature that needs them) because that's what
# app_catalog.py's "salesforce" entry marks view=True for; adding a feature
# that uses Opportunity/Lead/Case needs their real fields marked there, not
# invented here.
FIELD_CATALOG = app_catalog.field_catalog("salesforce")

# Capability 4 (write-usecase field config, e.g. "create a Contact from
# Hiver") — the write-flagged analogue of FIELD_CATALOG above, same DERIVED
# relationship to app_catalog.py. apps/setup.py's write-usecase step reads
# this; the existing view-usecase step above is untouched by its existence.
WRITABLE_FIELD_CATALOG = app_catalog.writable_field_catalog("salesforce")

# clickup_create_task_from_hiver's field-config step reads this instead —
# same DERIVED relationship, second app proving the catalog is genuinely
# per-app rather than hand-tied to Salesforce.
CLICKUP_WRITABLE_FIELD_CATALOG = app_catalog.writable_field_catalog("clickup")
