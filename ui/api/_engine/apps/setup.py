"""Track A: a real guided setup flow for an existing App feature — NOT an
automation (no trigger/conditions/action chain), but not a single yes/no
check either. Per the 2026-08-18 product spec ("Apps Activation Steps:
Usecase-wise steps"), enabling a feature is:

  1. Authentication            -- is the app connected? (connected_apps.py)
  2. Record-level visibility   -- which objects should this feature show?
  3. Field config - Read       -- for each object, which fields (from a
                                  live "describe" call, not a fixed list)?
  4. Confirm & enable

resolve_setup() walks these in order, one blocking question at a time —
the same MAX-1-thing-at-a-time discipline automation/validator.py uses,
applied to a much smaller, enum-only vocabulary (object/field names are
picked from schema.FEATURES[...]['object_choices'] / schema.FIELD_CATALOG,
never free text), which is why this doesn't need validator.py's
provenance/entity-resolution machinery — there's nothing to hallucinate
when the only legal answers are items from a list the code itself offered.

This is apps/'s peer of automation/validator.py — the resolver half of
Track A's own track, not a helper bolted onto the automation engine. Track A
has no trigger/conditions/actions to validate, and forcing it through that
shape kept producing exactly the "still works with the automation schema"
bug the automation/ vs apps/ package split fixes (see router.py).

GENERIC: resolve_setup()'s step order and question-planning work for any
FEATURES entry that declares object_choices whose objects all have a
FIELD_CATALOG entry.
SHAPED BY ONE EXAMPLE: only Account/Contact have a FIELD_CATALOG entry.
Field config - Write, Prefill fields, and Quick Access (the product spec's
other listed setup steps) are explicitly NOT built here — they belong to
"Managing CRM Records from Hiver", a use case out of scope for this pass.
"""
import connected_apps
import salesforce_mock

from . import schema

MAX_QUESTIONS = 1  # Track A asks ONE thing per turn — a short, ordered wizard,
                   # not a bundle (unlike validator.py's up-to-3: this flow is
                   # inherently sequential, each answer changes what's next)


def list_features(app):
    """Every Track A feature available for one connected app, id -> spec.
    Used by the Apps-panel listing (serve_apps.py) to show what's offered
    before any setup conversation starts."""
    return {fid: f for fid, f in schema.FEATURES.items() if f["app"] == app}


def _question(slot, prompt, options, multiple=False):
    return {"slot": slot, "prompt": prompt, "kind": "choice",
            "options": options, "multiple": multiple,
            "allow_other": False, "other_hint": ""}


def _result(status, errors=None, missing=None, feature=None, progress=None):
    missing = missing or []
    return {
        "status": status,
        "errors": errors or [],
        "questions": [m["prompt"] for m in missing][:MAX_QUESTIONS],
        "questions_structured": missing[:MAX_QUESTIONS],
        "feature": feature,
        "progress": progress or {},
    }


def resolve_setup(feature_id, feature_setup, apps_ws):
    """feature_setup: the slots apps/extract.py filled this turn from the
    WHOLE conversation so far — connect_requested, objects, <object>_fields
    per selected object, confirm. Returns an automation/validator.py-shaped
    dict (status/errors/questions/questions_structured) plus `feature` (set
    only once enabled) and `progress` (what's been resolved so far, for the
    UI to show a running summary the same way RuleCard shows partial
    WHEN/IF/THEN)."""
    f = schema.FEATURES.get(feature_id)
    if f is None:
        return _result("invalid", errors=[f"unknown feature '{feature_id}'"])

    feature_setup = feature_setup or {}
    app = f["app"]

    # ---- step 1: authentication ---------------------------------------------
    if feature_setup.get("connect_requested"):
        connected_apps.connect(apps_ws, app)
    unmet = connected_apps.prerequisites_met(apps_ws, app, f["prerequisites"])
    progress = {"connected": not unmet}
    if unmet:
        labels = [connected_apps.PREREQUISITE_LABELS.get(p, p) for p in unmet]
        action = connected_apps.PREREQUISITE_ACTIONS.get(unmet[0])
        if action is None:
            # no one-click fix exists for this gate (e.g. an org-side config
            # Hiver can't flip) — an honest blocker, not a fake CTA
            return _result("invalid", errors=[f"'{f['name']}' isn't usable yet — "
                                              + "; ".join(labels)], progress=progress)
        q = _question("feature_setup.connect",
                      f"{f['name']} needs {labels[0]} first. Connect it now?",
                      [{"label": action["label"], "value": action["phrase"]}])
        return _result("needs_info", missing=[q], progress=progress)

    # ---- step 2: record-level visibility (which objects) --------------------
    choices = f.get("object_choices", [])
    requested = feature_setup.get("objects") or []
    bad = [o for o in requested if o not in choices]
    objects = [o for o in requested if o in choices]
    progress["objects"] = objects
    if not objects:
        errors = ([f"'{b}' isn't one of the records {f['name']} can show "
                   f"({', '.join(choices)})" for b in bad])
        q = _question("feature_setup.objects",
                      f"Which records should {f['name']} show?",
                      [{"label": o, "value": o} for o in choices], multiple=True)
        return _result("needs_info", errors=errors, missing=[q], progress=progress)

    # ---- step 3: field config - read (per selected object) ------------------
    fields_by_object = {}
    for obj in objects:
        catalog = schema.FIELD_CATALOG.get(obj)
        if catalog is None:
            # a real object with no field catalog yet (e.g. Opportunity/Lead/
            # Case) — an honest gap, not a fake field list; see schema.py
            return _result("invalid",
                           errors=[f"'{obj}' field selection isn't built yet"],
                           progress=progress)
        available = catalog["standard"] + catalog["custom"]
        chosen_key = f"{obj.lower()}_fields"
        requested_fields = feature_setup.get(chosen_key) or []
        chosen = [c for c in requested_fields if c in available]
        if not chosen:
            described = salesforce_mock.describe_fields(obj)
            q = _question(
                f"feature_setup.{chosen_key}",
                f"Which {obj} fields should show? (from Salesforce: "
                + ", ".join(x["name"] for x in described["fields"]) + ")",
                [{"label": x["name"], "value": x["name"]} for x in described["fields"]],
                multiple=True)
            progress["fields_by_object"] = fields_by_object
            return _result("needs_info", missing=[q], progress=progress)
        fields_by_object[obj] = chosen
    progress["fields_by_object"] = fields_by_object

    # ---- step 4: confirm ------------------------------------------------------
    if not feature_setup.get("confirm"):
        summary = "; ".join(f"{o} ({', '.join(fs)})" for o, fs in fields_by_object.items())
        q = _question("feature_setup.confirm", f"Enable {f['name']} — {summary}?",
                      [{"label": "Yes, enable it", "value": "yes, enable it"},
                       {"label": "Not yet", "value": "not yet"}])
        return _result("needs_info", missing=[q], progress=progress)

    return _result("complete", progress=progress, feature={
        "id": feature_id, "app": app, "name": f["name"], "description": f["description"],
        "objects": objects, "fields_by_object": fields_by_object,
    })
