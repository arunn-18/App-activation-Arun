"""Track A: enabling an existing App feature — NOT an automation.

Kept deliberately separate from the rule-spec engine (schema.py's
ACTIONS/RECIPES, extract.py, validator.py, copilot.py): Track A has no
trigger, no conditions, no chain of steps to run per conversation — it is a
one-time "does this app satisfy what the feature needs?" check. Forcing that
through the automation schema would mean modeling a non-automation as one
just to reuse code that doesn't actually fit its shape (see schema.py's
FEATURES comment for the same point from the data side).

There is no clarification loop here on purpose: the one feature that exists
needs no input from the admin beyond which app/feature they picked — the
only question is whether its prerequisites (schema.FEATURES[...]
["prerequisites"], checked the same way RECIPES' are in validator.py) are
already met. A future feature that needs its own setup slot (e.g. "which
fields to show") would need a real question-planning path; don't invent one
now for a feature that doesn't need it — mirror validator.py's
missing/provenance pattern when that day comes.
"""
import connected_apps
import schema


def list_features(app):
    """Every Track A feature available for one connected app, id -> spec."""
    return {fid: f for fid, f in schema.FEATURES.items() if f["app"] == app}


def enable_feature(feature_id, apps_ws):
    """Attempt to enable a Track A feature. Returns
    {"status": "complete" | "invalid", "errors": [...], "feature"?: {...}} —
    the same three-field shape as validator.validate()'s status/errors, so a
    UI handling both tracks doesn't need two different result shapes."""
    f = schema.FEATURES.get(feature_id)
    if f is None:
        return {"status": "invalid", "errors": [f"unknown feature '{feature_id}'"]}
    unmet = connected_apps.prerequisites_met(apps_ws, f["app"], f["prerequisites"])
    if unmet:
        labels = [schema.PREREQUISITE_LABELS.get(p, p) for p in unmet]
        return {"status": "invalid",
                "errors": [f"can't enable '{f['name']}' yet — " + "; ".join(labels)]}
    return {"status": "complete", "errors": [],
            "feature": {"id": feature_id, "app": f["app"], "name": f["name"],
                        "description": f["description"]}}
