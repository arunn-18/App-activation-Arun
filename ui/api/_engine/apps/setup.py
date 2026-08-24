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
import app_catalog
import clickup_mock
import connected_apps
import salesforce_mock
import workspace as wsmod

from . import schema

# Display casing for prose ("from Salesforce:", "from ClickUp:") — kept here
# rather than app.title() because "clickup".title() gives "Clickup", not the
# product's real capitalization.
APP_DISPLAY_NAMES = {"salesforce": "Salesforce", "clickup": "ClickUp"}

# Step 3's catalog + describe-call source, one entry per onboarded app — the
# same "config, not a new branch" cost every other per-app extension in this
# engine already pays (NATIVE_ACTIONS, connected_apps.json, app_catalog.py's
# CATALOG). Adding a THIRD app's write feature means one entry here, not a
# new if/elif.
_WRITABLE_CATALOG_BY_APP = {
    "salesforce": (schema.WRITABLE_FIELD_CATALOG, salesforce_mock.describe_writable_fields),
    "clickup": (schema.CLICKUP_WRITABLE_FIELD_CATALOG, clickup_mock.describe_writable_fields),
}

# test_create()'s create-op dispatch, by (app, object_name) — mirrors
# _WRITABLE_CATALOG_BY_APP's "config, not a branch" shape. Each op takes
# {api_field_name: value} and returns the mock's real created-record dict;
# signatures are untouched so automation/executor.py's own calls into these
# same mock functions (capability 5/6) are unaffected.
_CREATE_OPS = {
    ("salesforce", "Contact"): lambda api_fields: salesforce_mock.create_contact(api_fields),
    ("clickup", "Task"): lambda api_fields: clickup_mock.create_task(**api_fields),
}

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


def _result(status, errors=None, missing=None, feature=None, progress=None, preview=None):
    missing = missing or []
    return {
        "status": status,
        "errors": errors or [],
        "questions": [m["prompt"] for m in missing][:MAX_QUESTIONS],
        "questions_structured": missing[:MAX_QUESTIONS],
        "feature": feature,
        "progress": progress or {},
        "preview": preview,
    }


def preview_feature(feature, test_contact_email):
    """"Test on a real conversation" (capability 7) for a VIEW feature: show
    the REAL field values this feature would display for one real contact,
    by actually querying the mock service — the Track A analogue of
    automation/executor.py's connector test-run, for a mechanism with no
    chain, no terminal action: just "does the data actually show up." A
    contact-not-found lookup is a real, valid outcome (the same "no_match,
    not an error" stance the connector executor already takes), never
    faked with placeholder values.

    `feature`: the completed feature dict resolve_setup() already returned
    (objects/fields_by_object — which fields were CHOSEN, by display label,
    not the object's full field list).

    SHAPED BY ONE EXAMPLE: only resolves Account/Contact records — the two
    objects this pass's one view feature actually offers. A future feature
    covering Opportunity/Case needs its own record-source line added here,
    the same "supply the real mapping, don't invent one" discipline
    app_catalog.py's own comments already ask for."""
    contacts = salesforce_mock.find_contact_by_email(test_contact_email).get("records") or []
    if not contacts:
        return {"status": "no_match", "contact_email": test_contact_email,
                "reason": f"no Salesforce contact found for '{test_contact_email}'"}
    contact = contacts[0]
    records_by_object = {"Contact": contact}
    accounts = salesforce_mock.get_account(contact.get("account_id")).get("records") or []
    if accounts:
        records_by_object["Account"] = accounts[0]

    values_by_object = {}
    for obj, chosen_labels in (feature.get("fields_by_object") or {}).items():
        record = records_by_object.get(obj)
        if record is None:
            continue
        api_by_label = app_catalog.field_by_label(feature["app"], obj)
        values_by_object[obj] = {label: record.get(api_by_label.get(label))
                                 for label in chosen_labels}
    return {"status": "ok", "contact_email": test_contact_email,
            "values_by_object": values_by_object}


def test_create(feature, field_values):
    """"Test on a real conversation" (capability 7) for a WRITE feature:
    actually create a mock record from admin-submitted form values — the
    write analogue of preview_feature() above. A view feature's test shows
    EXISTING data; a write feature has no existing record to show, so
    testing it means the create genuinely has to happen (against the mock,
    never a real org), not a preview of anything. A live test surfaced the
    gap this closes: the "want to test it?" nudge was showing for a write
    feature with nothing wired up to act on it — see copilot._is_write_
    feature()'s own comment for that story.

    `feature`: the completed feature dict resolve_setup() already returned
    (objects/fields_by_object — which fields the admin chose to expose, by
    display label — same shape preview_feature() takes). `field_values` is
    {label: value} submitted from the test form; a label outside
    fields_by_object is REJECTED, not silently dropped — the same "never
    let a submission smuggle in something not configured" discipline every
    provenance check in this engine already holds itself to.

    SHAPED BY TWO EXAMPLES: creates a Salesforce Contact or a ClickUp Task —
    the two write features this pass offers, dispatched via _CREATE_OPS by
    (app, object_name). A future write feature covering another object
    needs its own create_<object> op in that app's mock service and one
    more _CREATE_OPS entry, the same "config, not a branch" discipline
    _WRITABLE_CATALOG_BY_APP above already pays."""
    fields_by_object = feature.get("fields_by_object") or {}
    object_name = next(iter(fields_by_object), None)
    op = _CREATE_OPS.get((feature["app"], object_name))
    if op is None:
        return {"status": "error",
                "reason": f"don't know how to create a {object_name or 'record'} yet"}
    chosen_labels = set(fields_by_object[object_name])
    unknown = [label for label in field_values if label not in chosen_labels]
    if unknown:
        return {"status": "error",
                "reason": f"not exposed by this feature: {', '.join(unknown)}"}
    api_by_label = app_catalog.field_by_label(feature["app"], object_name)
    api_fields = {api_by_label[label]: value for label, value in field_values.items()
                 if label in api_by_label and value not in (None, "")}
    record = op(api_fields)
    return {"status": "ok", "object": object_name, "record": record}


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
    if is_write:
        catalog_by_object, describe = _WRITABLE_CATALOG_BY_APP[app]
    else:
        # no non-Salesforce view feature exists yet — see schema.py's
        # SHAPED-BY-TWO-EXAMPLES note; the write branch above is the one
        # that's genuinely per-app today.
        catalog_by_object, describe = schema.FIELD_CATALOG, salesforce_mock.describe_fields
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
                f"Which {obj} fields should {question_verb}? (from "
                f"{APP_DISPLAY_NAMES.get(app, app.title())}: "
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

    feature_out = {
        "id": feature_id, "app": app, "name": f["name"], "description": f["description"],
        "objects": objects, "fields_by_object": fields_by_object, "inboxes": inboxes,
        # the UI needs this to decide preview vs. test_create rendering —
        # never inferred client-side from field names or anything else.
        "kind": f.get("kind", "view"),
    }
    # "test on a real conversation" (capability 7) — a courtesy shown
    # ALONGSIDE completion, never blocking it: the feature is already fully
    # enabled without this. is_write is excluded on purpose — a write
    # feature creates a NEW record, there's no existing real data to show a
    # preview of yet (see preview_feature()'s own SHAPED-BY-ONE-EXAMPLE note).
    preview = None
    if not is_write and feature_setup.get("test_contact_email"):
        preview = preview_feature(feature_out, feature_setup["test_contact_email"])
    return _result("complete", progress=progress, feature=feature_out, preview=preview)
