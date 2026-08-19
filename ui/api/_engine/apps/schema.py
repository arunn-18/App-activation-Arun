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
object_choices) and the FIELD_CATALOG shape (object -> standard/custom field
lists) generalize to any future app/feature — see apps/setup.py's
resolve_setup() for the step order that walks them.

SHAPED BY HAVING SEEN TWO REAL USE CASES (per the 2026-08-18 product spec,
"Apps Activation Steps: Usecase-wise steps" — a CSV listing every Salesforce
use case and its setup steps): only ONE feature is built
(salesforce_account_contact_details), covering the first CRM use case
("Viewing account & contact details"). The second use case in the same spec
("Smart routing to right owner / auto-assignment") is Track B — it's an
automation with a trigger, so it lives in automation/schema.py's RECIPES,
not here. The OTHER use cases in the same spec (Managing CRM Records from
Hiver; Syncing Hiver conversations with SF records) are explicitly NOT
built — they need Field config - Write, Prefill fields, and Sync steps this
module doesn't implement; don't stretch FEATURES to fake them.
"""

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
