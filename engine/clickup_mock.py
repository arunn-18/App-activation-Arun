"""Mock ClickUp service — the SECOND app's adapter, existing specifically to
prove capability 5 (native app-action automations) generalizes past
Salesforce: onboarding ClickUp needed exactly this file (one op, mirroring
the "call an API, don't fake it" stance salesforce_mock.py already takes),
a connected_apps.json entry (auth), and a NATIVE_ACTIONS entry
(automation/schema.py) — no engine code changed to add it.

Native actions (capability 5) are NOT the same mechanism as Track B's
connector recipes/dynamic plans (capability 6) — Hiver's product has a
real, pre-built "Create ClickUp task" action block; there is no object/field
catalog to query, no chain to compose, just this one call. That's why
ClickUp has no app_catalog.py entry: this capability doesn't need one.

Prototype returns a fixed shape; production would call ClickUp's real REST
API (https://api.clickup.com/api/{version}/...) with the org's connected
credentials, at whatever version connected_apps.api_version(apps_ws,
"clickup") is pinned to — the same version-pinning guardrail
salesforce_mock.py's docstring already flags.
"""
import itertools

_task_ids = itertools.count(1001)


def create_task(list_name, title, description=None, assignee=None, due_date=None,
                priority=None):
    """Mock 'create a task' call. Always succeeds in this prototype (there
    is no real ClickUp org to reject an unknown list against) — returns a
    real-shaped response {"id", "list", "name", "url", ...} so a test-run
    capture looks like what production would actually show, not an ad hoc
    double. description/assignee/due_date/priority are genuinely OPTIONAL —
    a ClickUp task doesn't need any of them to exist, only a list and a
    title — so each is included in the response only when actually given,
    never as a fake empty placeholder."""
    task_id = next(_task_ids)
    task = {"id": f"CU-{task_id}", "list": list_name, "name": title,
            "url": f"https://app.clickup.com/t/{task_id}"}
    if description:
        task["description"] = description
    if assignee:
        task["assignee"] = assignee
    if due_date:
        task["due_date"] = due_date
    if priority:
        task["priority"] = priority
    return task
