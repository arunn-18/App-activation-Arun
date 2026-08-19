"""Connected-apps fixture: which third-party apps this workspace has
connected, and the prerequisite flags each one satisfies.

Same split as workspace.py, one level up: this is state about the APPS
themselves (is Salesforce connected? is Account Team enabled?), not about
Hiver entities (tags/agents/inboxes) — kept separate so the Apps-panel entry
point and the connector/Track-A prerequisite checks have one clear source,
instead of overloading workspace.json with unrelated app-connection state.
Prototype reads connected_apps.json; production would hit the apps/
integrations service.

GENERIC: load() / prerequisites_met() work for any app entry this fixture
grows. SHAPED BY ONE EXAMPLE: only Salesforce is populated, and its two flags
(salesforce_connected, account_team_enabled) are named for what THIS ONE
recipe + Track A feature need — not a general taxonomy of what an app
prerequisite could be. A prerequisite that needs a configured VALUE, not just
a yes/no, doesn't fit this shape yet.

PREREQUISITE_LABELS/PREREQUISITE_ACTIONS live here (not in either track's
schema.py) because "is this app connected/configured enough?" is the SAME
question for both automation/schema.py's RECIPES and apps/schema.py's
FEATURES — genuinely shared vocabulary, not owned by either track.
"""
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "connected_apps.json"

# prerequisite flag -> what it means, for error/status messages
PREREQUISITE_LABELS = {
    "salesforce_connected": "the Salesforce app must be connected",
    "account_team_enabled": "Salesforce Account Team must be enabled with a CSM role",
}

# prerequisite flag -> the one-click fix, when the flag can be satisfied by a
# real (mocked) connect() action rather than just a static error. `phrase` is
# what a click composes into chat; not every prerequisite has one yet (e.g.
# account_team_enabled has no mock "enable Account Team" action — it's
# assumed already configured on the Salesforce side).
PREREQUISITE_ACTIONS = {
    "salesforce_connected": {"label": "Connect Salesforce", "phrase": "connect salesforce"},
}


def load(path=DEFAULT_PATH):
    return json.loads(Path(path).read_text())


def is_connected(apps_ws, app):
    return bool((apps_ws.get("connected_apps") or {}).get(app, {}).get("connected"))


def prerequisites_met(apps_ws, app, prerequisite_keys):
    """Returns the SUBSET of prerequisite_keys that are NOT satisfied (empty
    list = all met). Never raises on an unknown app — an app with no entry
    simply satisfies none of its prerequisites."""
    flags = (apps_ws.get("connected_apps") or {}).get(app, {}).get("prerequisites") or {}
    return [p for p in prerequisite_keys if not flags.get(p)]


def connect(apps_ws, app):
    """Mock 'complete the connect/OAuth flow' action — the Authentication
    step's one-click fix (PREREQUISITE_ACTIONS above). Flips `connected`
    and every prerequisite flag ALREADY REGISTERED for this app to True, in
    place, so the connection persists for the rest of this server process —
    the same in-memory-only demo state as the rule log / workspace fixtures
    elsewhere in this engine. Nothing is actually called against a real
    Salesforce org.

    SHAPED BY ONE EXAMPLE: this blanket-flips every registered prerequisite,
    which is only correct because connecting Salesforce is this app's ONLY
    interactive fix today (account_team_enabled has no CTA — it's assumed
    already configured on the org and just starts true in the fixture). A
    future prerequisite that represents a real third-party CONFIG step
    (not fixable by "connect") needs its own action, not this blanket flip."""
    entry = apps_ws.setdefault("connected_apps", {}).setdefault(
        app, {"connected": False, "prerequisites": {}})
    entry["connected"] = True
    for p in entry.get("prerequisites", {}):
        entry["prerequisites"][p] = True
    return entry
