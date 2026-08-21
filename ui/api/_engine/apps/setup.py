"""Track A: a real guided setup flow for an existing App feature — NOT an
automation (no trigger/conditions/action chain), but not a single yes/no
check either. Per the 2026-08-18 product spec ("Apps Activation Steps:
Usecase-wise steps"), enabling a feature is:

  1. Authentication            -- is the app connected? (connected_apps.py)
  2. Record-level visibility   -- which objects should this feature show?
  3. Field config              -- Read (kind="view") or Write (kind="write",
                                  capability 4) — for each object, which
                                  fields (from a live "describe" call, not a
                                  fixed list)? A write-kind feature asks
                                  which fields agents can FILL IN when
                                  creating a record, reading
                                  WRITABLE_FIELD_CATALOG instead of
                                  FIELD_CATALOG — a genuinely separate
                                  branch (see below), not a wording tweak on
                                  the view branch.
  4. Enable                    -- which shared inbox(es) should this be
                                  turned on for? (workspace.py's
                                  shared_inboxes) Picking inbox(es) here IS
                                  the enable action — not a separate plain
                                  "Enable?" yes/no CTA, since a feature like
                                  this is meaningfully scoped per inbox, not
                                  global to the whole workspace.

resolve_setup() walks these in order, one blocking question at a time —
the same MAX-1-thing-at-a-time discipline automation/validator.py uses,
applied to a much smaller, enum-only vocabulary (object/field names are
picked from schema.FEATURES[...]['object_choices'] / schema.FIELD_CATALOG /
schema.WRITABLE_FIELD_CATALOG, never free text), which is why this doesn't
need validator.py's provenance/entity-resolution machinery — there's
nothing to hallucinate when the only legal answers are items from a list
the code itself offered.

This is apps/'s peer of automation/validator.py — the resolver half of
Track A's own track, not a helper bolted onto the automation engine. Track A
has no trigger/conditions/actions to validate, and forcing it through that
shape kept producing exactly the "still works with the automation schema"
bug the automation/ vs apps/ package split fixes (see router.py).

GENERIC: resolve_setup()'s step order and question-planning work for any
FEATURES entry that declares object_choices whose objects all have a
FIELD_CATALOG (view) or WRITABLE_FIELD_CATALOG (write) entry — adding a
feature is a data entry in apps/schema.py's FEATURES plus real fields
marked view/write in app_catalog.py, no changes needed here.
SHAPED BY HAVING SEEN TWO EXAMPLES: only Account/Contact have catalog
entries at all, and only the two FEATURES entries that exist (one view, one
write) are wired up. Prefill fields, Quick Access, and Syncing Hiver
conversations with SF records (the product spec's other listed setup
steps) are explicitly NOT built here — out of scope for this pass.
"""
import connected_apps
import salesforce_mock
import workspace as wsmod

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


def resolve_setup(feature_id, feature_setup, apps_ws, ws=None):
    """feature_setup: the slots apps/extract.py filled this turn from the
    WHOLE conversation so far — connect_requested, objects, <object>_fields
    per selected object, inboxes. Returns an automation/validator.py-shaped
    dict (status/errors/questions/questions_structured) plus `feature` (set
    only once enabled) and `progress` (what's been resolved so far, for the
    UI to show a running summary the same way RuleCard shows partial
    WHEN/IF/THEN). `ws`: the entity workspace fixture (for shared_inboxes) —
    defaults to the demo fixture like connected_apps.py's own load() does,
    so a caller that forgets to pass it still gets the real inbox list
    rather than an empty one."""
    f = schema.FEATURES.get(feature_id)
    if f is None:
        return _result("invalid", errors=[f"unknown feature '{feature_id}'"])

    feature_setup = feature_setup or {}
    app = f["app"]
    # kind="write" (capability 4) branches step 2's wording and step 3's
    # catalog/describe-call below — computed once here since both need it.
    # The view kind's behavior (default) is unchanged by this branch's
    # existence.
    is_write = f.get("kind") == "write"

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
        record_verb = "create" if is_write else "show"
        errors = ([f"'{b}' isn't one of the records {f['name']} can {record_verb} "
                   f"({', '.join(choices)})" for b in bad])
        q = _question("feature_setup.objects",
                      f"Which records should {f['name']} {record_verb}?",
                      [{"label": o, "value": o} for o in choices], multiple=True)
        return _result("needs_info", errors=errors, missing=[q], progress=progress)

    # ---- step 3: field config — read (view) or write (capability 4) ---------
    # kind="write" is a genuinely separate branch, not a parameter tweak on
    # the view branch below: different catalog, different describe call,
    # different question wording ("show" vs "fill in when creating one").
    # The view branch (default, existing behavior) is UNCHANGED by this
    # branch's existence — same catalog, same describe call, same wording.
    catalog_by_object = schema.WRITABLE_FIELD_CATALOG if is_write else schema.FIELD_CATALOG
    describe = (salesforce_mock.describe_writable_fields if is_write
               else salesforce_mock.describe_fields)
    question_verb = "fill in when creating one" if is_write else "show"

    fields_by_object = {}
    for obj in objects:
        catalog = catalog_by_object.get(obj)
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
            described = describe(obj)
            q = _question(
                f"feature_setup.{chosen_key}",
                f"Which {obj} fields should {question_verb}? (from Salesforce: "
                + ", ".join(x["name"] for x in described["fields"]) + ")",
                [{"label": x["name"], "value": x["name"]} for x in described["fields"]],
                multiple=True)
            progress["fields_by_object"] = fields_by_object
            return _result("needs_info", missing=[q], progress=progress)
        fields_by_object[obj] = chosen
    progress["fields_by_object"] = fields_by_object

    # ---- step 4: enable — which shared inbox(es) this should apply to -------
    # naming inbox(es) here IS the enable action; there is no separate plain
    # yes/no CTA, since this feature is meaningfully scoped per inbox, not a
    # single global on/off switch.
    ws = ws or wsmod.load()
    inbox_choices = ws.get("shared_inboxes", [])
    requested_inboxes = feature_setup.get("inboxes") or []
    inbox_names = {i["name"] for i in inbox_choices}
    bad_inboxes = [x for x in requested_inboxes if x not in inbox_names]
    inboxes = [x for x in requested_inboxes if x in inbox_names]
    progress["inboxes"] = inboxes
    if not inboxes:
        errors = [f"'{b}' isn't a shared inbox in this workspace" for b in bad_inboxes]
        summary = "; ".join(f"{o} ({', '.join(fs)})" for o, fs in fields_by_object.items())
        q = _question("feature_setup.inboxes",
                      f"{f['name']} is ready — {summary}. Which shared inbox(es) "
                      "should it be enabled for?",
                      [{"label": i["name"], "value": i["name"]} for i in inbox_choices],
                      multiple=True)
        return _result("needs_info", errors=errors, missing=[q], progress=progress)

    return _result("complete", progress=progress, feature={
        "id": feature_id, "app": app, "name": f["name"], "description": f["description"],
        "objects": objects, "fields_by_object": fields_by_object, "inboxes": inboxes,
    })
