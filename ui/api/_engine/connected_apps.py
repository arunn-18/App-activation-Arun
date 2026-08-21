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
grows — onboarding an app's auth is a data entry here (connected +
api_version + whatever named prerequisite flags it needs), never a code
change. SHAPED BY HAVING SEEN TWO EXAMPLES: Salesforce's two flags
(salesforce_connected, account_team_enabled) are named for what its recipe +
Track A features need; ClickUp's one flag (clickup_connected) is named for
what its native create_task action (automation/schema.py's NATIVE_ACTIONS)
needs — not a general taxonomy of what an app prerequisite could be. A
prerequisite that needs a configured VALUE, not just a yes/no, doesn't fit
this shape yet.

api_version (see api_version() below) is a THIRD kind of per-app state,
distinct from a prerequisite flag: not "is this satisfied yes/no" but "which
API version is this connection's auth actually scoped to." Real integrations
(Salesforce especially) issue an access token against a specific API
version, and calls must target that SAME version's endpoints — this fixture
is where that pin lives, so a real (non-mock) API client has exactly one
place to read it from, never a per-call guess.

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
    "clickup_connected": "the ClickUp app must be connected",
}

# prerequisite flag -> the one-click fix, when the flag can be satisfied by a
# real (mocked) connect() action rather than just a static error. `phrase` is
# what a click composes into chat; not every prerequisite has one yet (e.g.
# account_team_enabled has no mock "enable Account Team" action — it's
# assumed already configured on the Salesforce side).
PREREQUISITE_ACTIONS = {
    "salesforce_connected": {"label": "Connect Salesforce", "phrase": "connect salesforce"},
    "clickup_connected": {"label": "Connect ClickUp", "phrase": "connect clickup"},
}


def load(path=DEFAULT_PATH):
    return json.loads(Path(path).read_text())


def is_connected(apps_ws, app):
    return bool((apps_ws.get("connected_apps") or {}).get(app, {}).get("connected"))


def api_version(apps_ws, app):
    """The API version this connection is PINNED to — set once, at real
    OAuth/connect time, by whatever version the app's auth handshake was
    actually issued against (Salesforce, notably: an access token is
    scoped to the API version the connected app's setup used, and a call
    against a DIFFERENT version's endpoint is not just "maybe fine", it can
    silently see different field visibility or outright fail).

    THE GUARDRAIL: this value is never inferred, never defaulted to
    "latest", and never chosen per-call — a real (non-mock)
    describe_object()/query() implementation must read it from HERE and
    build its endpoint path from it (e.g.
    f"/services/data/{api_version}/sobjects/...") every single time. If a
    connection has no pinned version, treat it as NOT usable for API calls
    at all — that is a broken/incomplete connection, not something to patch
    over with a guess. None means exactly that: no pinned version on file."""
    return (apps_ws.get("connected_apps") or {}).get(app, {}).get("api_version")


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
