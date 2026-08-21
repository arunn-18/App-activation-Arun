"""Mock Salesforce service — SHARED between both tracks: automation/
executor.py's connector recipe chain calls find_contact_by_email/
get_account_team_csm (and, for a dynamically-composed plan, the generic
query()); apps/setup.py's Track A field-config step calls describe_fields.
It lives at the top level (not inside either automation/ or apps/) because
it isn't automation- or app-setup-specific — it's "what Salesforce itself
would say," which both tracks legitimately need.

Functions here are the "ops" automation/executor.py's chain runner calls by
name (recipe step {"kind": "api_call", "op": "find_contact_by_email", ...}).
Each returns a dict shaped like a real Salesforce REST/SOQL response
envelope ({"totalSize", "done", "records": [...]})  so the raw response an
executor test-run captures and shows the admin looks like what production
would actually see, not an ad hoc test double.

The CSM-vs-AE filtering lives HERE, in get_account_team_csm — it queries
"the CSM" the same way a real integration would (SOQL
`WHERE TeamMemberRole = 'CSM'`), not as generic chain logic in executor.py.
See the SHAPED-BY-ONE-EXAMPLE note on automation/schema.py's RECIPES for why
that's a deliberate scoping choice, not an oversight.

query()/describe_object()/list_objects() are the GENERIC primitives a
dynamically-composed connector plan (automation/planner.py) uses instead of
a named, hand-written op — every hardcoded op below (find_contact_by_email,
get_account_team_csm, get_account_team) is itself expressible as one query()
call with the right `where` filter; they stay as named wrappers only
because RECIPES' one hand-vetted chain and its tests already refer to them
by name, not because query() can't do what they do.

Prototype reads salesforce_fixture.json; production would call the real
Salesforce API with the org's connected credentials — and every one of
those calls MUST target connected_apps.api_version(apps_ws, "salesforce"),
the version this connection's auth was actually issued against, never
"latest" or an inferred default (see that function's docstring for why).
This mock makes no HTTP call at all, so there is no endpoint path to get
that wrong yet — but a real client built on this same op surface
(query/describe_object/list_objects) needs to thread that pinned version
into every request it builds.
"""
import json
from pathlib import Path

import salesforce_schema
from apps import schema as apps_schema

DEFAULT_PATH = Path(__file__).parent / "salesforce_fixture.json"


def load(path=DEFAULT_PATH):
    return json.loads(Path(path).read_text())


def _envelope(records):
    return {"totalSize": len(records), "done": True, "records": records}


def find_contact_by_email(email, fixture=None):
    fixture = fixture if fixture is not None else load()
    email_norm = str(email or "").strip().lower()
    matches = [c for c in fixture["contacts"] if c["email"].lower() == email_norm]
    return _envelope(matches)


def get_account(account_id, fixture=None):
    fixture = fixture if fixture is not None else load()
    matches = [a for a in fixture["accounts"] if a["account_id"] == account_id]
    return _envelope(matches)


def get_account_team_csm(account_id, fixture=None):
    """The CSM (role == 'CSM') on this account's team — never an AE or any
    other role, even when the account has one. Zero records means the
    account genuinely has no CSM assigned (a real, valid outcome — not an
    error), which is exactly the clean-failure case the executor must
    handle without an exception."""
    fixture = fixture if fixture is not None else load()
    matches = [m for m in fixture["account_team"]
              if m["account_id"] == account_id and m["role"] == "CSM"]
    return _envelope(matches)


def get_account_team(account_id, fixture=None):
    """The full account team, all roles — used by Track A's account/contact
    detail view (apps.schema.FEATURES), not by the CSM-autoassign recipe."""
    fixture = fixture if fixture is not None else load()
    matches = [m for m in fixture["account_team"] if m["account_id"] == account_id]
    return _envelope(matches)


def describe_fields(object_name):
    """Mock of a Salesforce object-describe call: standard + custom fields
    for one object. Track A's "Field config - Read" step calls this per
    object the admin selected, so the field list an admin picks from is
    never a hardcoded guess — same "call an API, don't fake it" stance as
    the rest of this mock service. Reads apps.schema.FIELD_CATALOG so the
    legal vocabulary apps/extract.py knows about and what this call actually
    returns can never drift apart."""
    catalog = apps_schema.FIELD_CATALOG.get(object_name)
    if catalog is None:
        return {"success": False, "object": object_name, "fields": []}
    fields = ([{"name": f, "kind": "standard"} for f in catalog["standard"]]
             + [{"name": f, "kind": "custom"} for f in catalog["custom"]])
    return {"success": True, "object": object_name, "fields": fields}


def describe_writable_fields(object_name):
    """Capability 4's analogue of describe_fields() above: which fields an
    admin can offer agents to FILL IN when creating a new record of this
    object (Track A's write-usecase step), not which fields to display.
    Reads apps.schema.WRITABLE_FIELD_CATALOG — a real describe API would
    tell you this from each field's `createable` flag; the mock's
    equivalent is app_catalog.py's per-field `write` flag."""
    catalog = apps_schema.WRITABLE_FIELD_CATALOG.get(object_name)
    if catalog is None:
        return {"success": False, "object": object_name, "fields": []}
    fields = ([{"name": f, "kind": "standard"} for f in catalog["standard"]]
             + [{"name": f, "kind": "custom"} for f in catalog["custom"]])
    return {"success": True, "object": object_name, "fields": fields}


# ------------------------------------------------------------- generic ops
# The primitives automation/planner.py's dynamically-composed connector
# plans run on, and the tools it explores the schema with before proposing
# one — see salesforce_schema.py for the closed object/field catalog these
# read from. A plan step can query() ONLY an object/field declared there;
# there is no way to reach fixture data outside that catalog through these
# functions, by construction (list_objects/describe_object are the only way
# the planner learns what exists, and query() itself validates against the
# same catalog it advertises).

def list_objects():
    """Every object name the generic query()/describe_object() ops know
    about — what automation/planner.py's list_objects tool returns, so the
    model can only ever plan against real, declared objects."""
    return sorted(salesforce_schema.OBJECTS)


def describe_object(object_name):
    """Field names + types for one object (see salesforce_schema.OBJECTS) —
    the generic, multi-object analogue of describe_fields() above (which is
    Track A's read-only display-field lookup, scoped to apps.schema's
    FIELD_CATALOG). Returns success: False for an object outside the
    catalog, the same honest-gap stance describe_fields() already takes."""
    obj = salesforce_schema.OBJECTS.get(object_name)
    if obj is None:
        return {"success": False, "object": object_name, "fields": []}
    return {"success": True, "object": object_name,
            "fields": [{"name": f, "type": t} for f, t in obj["fields"].items()]}


def query(object_name, where=None, fields=None, fixture=None):
    """Generic SOQL-like lookup: object_name -> the fixture table it maps to
    (salesforce_schema.OBJECTS[object_name]['table']), where -> a list of
    {"field", "eq"} equality filters, ANDed together (this is the one
    filter shape every hand-written op above already uses under the hood —
    get_account_team_csm is just this with where=[account_id, role=CSM]).
    `fields` is informational only (the full record is always returned, so
    a plan's extract_variables can pull whatever real field it needs);
    unknown object -> an empty, not-erroring envelope, same "no records"
    shape a real SOQL query against a nonexistent filter would produce —
    plan_validator.py is what actually rejects an unknown object/field
    before this is ever called."""
    obj = salesforce_schema.OBJECTS.get(object_name)
    if obj is None:
        return _envelope([])
    fixture = fixture if fixture is not None else load()
    records = fixture.get(obj["table"], [])
    where = where or []

    def matches(r):
        return all(str(r.get(w.get("field"))) == str(w.get("eq")) for w in where)

    return _envelope([r for r in records if matches(r)])
