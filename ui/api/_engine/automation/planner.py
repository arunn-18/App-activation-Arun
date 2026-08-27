"""Tools for composing a connector plan at extraction time, when the user's
ask is clearly Salesforce-connector-shaped (assign/tag a conversation based
on Salesforce data) but doesn't match any hand-vetted schema.RECIPES entry.
Mirrors workspace.py's TOOLS/dispatch pattern exactly — same reason: the
model explores real vocabulary through tool calls instead of guessing, and
whatever it proposes is re-verified in code afterward (plan_validator.py),
never trusted on the model's say-so alone.

These tools are READ-ONLY exploration (list_objects, describe_object) —
they let the model learn what's real before proposing a plan; they cannot
themselves run a query or produce a result. The plan itself (steps +
terminal) is part of the connector action's own structured output in
automation/extract.py's response schema, not something these tools return.
"""
import json

import salesforce_mock

TOOLS = [
    {"type": "function", "function": {
        "name": "list_objects",
        "description": ("List every Salesforce object name available for a connector "
                        "plan's query steps."),
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "describe_object",
        "description": ("Field names and types for one Salesforce object — call this "
                        "before referencing an object's fields in a plan step, the "
                        "same way you would call a real describe API."),
        "parameters": {"type": "object",
                       "properties": {"object_name": {"type": "string"}},
                       "required": ["object_name"]}}},
]


def dispatch(name, arguments):
    """Execute a tool call. Returns a JSON string for the tool message."""
    if name == "list_objects":
        return json.dumps({"objects": salesforce_mock.list_objects()})
    if name == "describe_object":
        return json.dumps(salesforce_mock.describe_object((arguments or {}).get("object_name", "")))
    return json.dumps({"error": f"unknown tool '{name}'"})
