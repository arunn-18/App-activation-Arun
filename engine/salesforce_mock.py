"""Mock Salesforce service for the one validated connector recipe
(salesforce_account_csm_autoassign, see schema.RECIPES).

Functions here are the "ops" executor.py's chain runner calls by name
(recipe step {"kind": "api_call", "op": "find_contact_by_email", ...}).
Each returns a dict shaped like a real Salesforce REST/SOQL response
envelope ({"totalSize", "done", "records": [...]})  so the raw response an
executor test-run captures and shows the admin looks like what production
would actually see, not an ad hoc test double.

The CSM-vs-AE filtering lives HERE, in get_account_team_csm — it queries
"the CSM" the same way a real integration would (SOQL
`WHERE TeamMemberRole = 'CSM'`), not as generic chain logic in executor.py.
See the SHAPED-BY-ONE-EXAMPLE note on schema.RECIPES for why that's a
deliberate scoping choice, not an oversight.

Prototype reads salesforce_fixture.json; production would call the real
Salesforce API with the org's connected credentials.
"""
import json
from pathlib import Path

import schema

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
    detail view (schema.FEATURES), not by the CSM-autoassign recipe."""
    fixture = fixture if fixture is not None else load()
    matches = [m for m in fixture["account_team"] if m["account_id"] == account_id]
    return _envelope(matches)


def describe_fields(object_name):
    """Mock of a Salesforce object-describe call: standard + custom fields
    for one object. Track A's "Field config - Read" step calls this per
    object the admin selected, so the field list an admin picks from is
    never a hardcoded guess — same "call an API, don't fake it" stance as
    the rest of this mock service. Reads schema.FIELD_CATALOG so the legal
    vocabulary extract.py knows about and what this call actually returns
    can never drift apart."""
    catalog = schema.FIELD_CATALOG.get(object_name)
    if catalog is None:
        return {"success": False, "object": object_name, "fields": []}
    fields = ([{"name": f, "kind": "standard"} for f in catalog["standard"]]
             + [{"name": f, "kind": "custom"} for f in catalog["custom"]])
    return {"success": True, "object": object_name, "fields": fields}
