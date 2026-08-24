"""In-memory feature-request log — the Discovery movement's "no match ->
auto-raises a feature request instead of failing silently" (Apps Activation
PRD, 2026-08-24). Every unsupported/unmappable ask the copilot escalates on
EITHER track is a real demand signal for a skill Hiver doesn't support yet;
this is where an admin's explicit "yes, log it" turns that signal into
something a PM can actually see.

Same "mock it, never fake it" discipline as connected_apps.py/salesforce_
mock.py: this is an in-memory, per-process log, not a real ClickUp/Jira
ticket — there is no real feature-request destination wired into this repo
yet (no credentials, no target board named). Swapping this for a real
integration means replacing log()'s body with a real API call; nothing
that reads this module's log() output needs to change shape when that
happens, since the log entry already carries every field the real
destination would need (app, request, why, track).

Logging is EXPLICIT and admin-confirmed, never silent or automatic — see
copilot._feature_request_offer()'s own docstring for why: this module only
ever gets called once an admin has actually said yes to the offer, the
same "never invent, always ask" discipline this whole engine already holds
every other side-effecting action to (connected_apps.connect(),
apps.setup.test_create()).
"""

_LOG = []


def log(app, request, why, track):
    """Record one feature request, deduped by (app, request) so re-answering
    "yes" for the same escalated ask twice (e.g. a later turn re-surfaces an
    unresolved gap) doesn't create a duplicate entry. Returns the entry (new
    or the existing match), never raises."""
    for entry in _LOG:
        if entry["app"] == app and entry["request"] == request:
            return entry
    entry = {"app": app, "request": request, "why": why, "track": track}
    _LOG.append(entry)
    return entry


def all_requests():
    """Every logged request so far, most recent last. Read-only snapshot —
    callers must not mutate the returned list."""
    return list(_LOG)


def reset():
    """Test-only: clear the log between test cases. Never called from
    production code paths."""
    _LOG.clear()
