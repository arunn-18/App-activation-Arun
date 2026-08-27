"""In-memory analytics event log — the Apps Activation PRD (2026-08-24)
names six Amplitude events for this flow (apps_activation_flow_started,
_capability_mapped, _feature_request_logged, _setup_step_completed,
_test_run, _activated). No real Amplitude project/key is wired into this
repo, so this is a stub sink with the same shape a real emit() call would
have — swapping it for a real Amplitude SDK call means replacing emit()'s
body only; every caller already passes (event, properties) in Amplitude's
own shape.

SCOPE NOTE: only EVENTS.FEATURE_REQUEST_LOGGED is actually emitted anywhere
in this codebase today (from copilot._feature_request_offer(), the one
piece of the Discovery movement this phase built). The other five are
listed here as named constants so a future wiring pass uses the exact
strings the PRD specifies rather than reinventing them, but instrumenting
flow_started/capability_mapped/setup_step_completed/test_run/activated
means touching many more call sites across both tracks and was
deliberately left out of this phase's scope — see PRD.md's Open Questions.
"""


class EVENTS:
    FLOW_STARTED = "apps_activation_flow_started"  # not yet emitted
    CAPABILITY_MAPPED = "apps_activation_capability_mapped"  # not yet emitted
    FEATURE_REQUEST_LOGGED = "apps_activation_feature_request_logged"
    SETUP_STEP_COMPLETED = "apps_activation_setup_step_completed"  # not yet emitted
    TEST_RUN = "apps_activation_test_run"  # not yet emitted
    ACTIVATED = "apps_activation_activated"  # not yet emitted


_LOG = []


def emit(event, properties=None):
    """Record one event. `properties` is a flat dict, same shape a real
    Amplitude track() call takes. Never raises -- an analytics failure must
    never break the conversation it's instrumenting."""
    entry = {"event": event, "properties": properties or {}}
    _LOG.append(entry)
    return entry


def all_events():
    """Every emitted event so far, most recent last. Read-only snapshot."""
    return list(_LOG)


def reset():
    """Test-only: clear the log between test cases. Never called from
    production code paths."""
    _LOG.clear()
