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
"""
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "connected_apps.json"


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
