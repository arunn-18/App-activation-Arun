"""Capability answers, from code — never from the model.

Mid-build, users ask what the builder can do ("apart from round robin is there
any other assignment that i can do?"). The extraction model only CLASSIFIES the
question (capability_question topic string); the answer is composed here from
schema.py, so every capability named is one the engine can actually build, and
what's out of scope is stated from the UNSUPPORTED list rather than omitted or
invented. Question turns are read-only: the draft rule is not touched.

App Activation only (2026-08-27 charter): this engine's whole job is
connecting Hiver to your apps — Track A app features (apps/schema.py's
FEATURES) and Track B app automations (a trigger/conditions shell around a
real connector action). Trigger/condition/generic-action vocabulary (tag,
assign, status, note, reply, inbox moves) is real and answered accurately
here, but it's SCAFFOLDING for an app automation, never the whole rule on
its own — copilot.py's own scope gate enforces the same boundary
downstream. "What's possible with Salesforce" spans BOTH tracks (view/
manage records AND connector automations), so the answer must too, or half
of what's actually built goes unmentioned. Anything else gets an honest
redirect.
"""
import re

from apps import schema as apps_schema
from automation import schema


def _kw_match(text, keys):
    """LEADING-word-boundary "does any of these keywords appear" check — a
    plain substring `k in text` (the original approach) is too promiscuous
    for short keys: "ai" matches inside "expl**ai**n"/"maint**ai**n", "tag"
    matches inside "advan**tag**e", "move" matches inside "re**move**",
    "api" matches inside "c**api**tal". A live test caught this for real: a
    meta-question containing "if I explain my workflow" got routed to the
    AI-variables topic purely because "explain" contains "ai" — an actual
    cause of the "irrelevant answer" complaint, not a hypothetical one.

    Deliberately only anchors the LEADING edge, not both: most keys here
    are intentional word STEMS, not whole words — "assign" must still
    match "assign**s**"/"assign**ed**"/"assign**ment**", "trigger" must
    still match "trigger**s**", "classif" must still match "classif**y**".
    A leading boundary alone already rules out every false-positive case
    above (in each, the short key sits mid-word with a LETTER immediately
    before it — "expl(ai)n", "advan(tag)e", "re(move)", "c(api)tal" — so
    requiring nothing-but-a-word-char right before the key is enough)."""
    return any(re.search(r"\b" + re.escape(k), text) for k in keys)

_OVERVIEW = (
    # App Activation only (2026-08-27 charter): this engine connects Hiver
    # to your apps, so the overview leads with the app-usecase framing
    # rather than reading as a generic rule-builder pitch with "talk to
    # another app" buried as one bullet among many — copilot.py's own
    # scope gate enforces the same thing downstream (see its own comment).
    "Describe what you want to happen, or what your workflow looks like, "
    "and I'll match it to what's actually built here — asking about "
    "anything I still need to fill in, and saying plainly if part of it "
    "isn't supported rather than guessing. Two kinds of thing I can set "
    "up, both connected to a real app. App features — enable once per "
    "workspace, no trigger involved: " + "; ".join(
        f"{f['name']} ({f['app'].title()})" for f in apps_schema.FEATURES.values())
    + ". And app automations — a rule fires on a trigger (new inbound/"
    "outbound conversations, incoming replies, outgoing email, or a "
    "conversation moved into the inbox), filters on conditions (sender/"
    "recipient addresses and domains, subject and body keywords, the "
    "conversation's current tags/assignee/status, day received, or an "
    "AI-extracted variable), then does something in the app it's connected "
    "to — a native action block (like creating a ClickUp task), a "
    "ready-made Salesforce recipe, or a Salesforce lookup composed on the "
    "fly for asks that fit the same shape. Every automation here needs at "
    "least one of those app actions; you can ALSO tag, assign, set status, "
    "add a note, send a reply or notification, or move the conversation "
    "between shared inboxes in the SAME rule, but none of those alone is "
    "something this engine builds on its own. Ask about any of these and "
    "I'll go deeper."
)

# keyword routes -> composed answers. Every claim traces to schema.py.
_TOPICS = [
    (("assign", "round robin", "round-robin", "rout", "owner", "rotate"),
     "Assignment comes in three forms: assign to one teammate ('assign it to "
     "Dana'), share among a set you name — either round robin (strictly in "
     "turn) or load balancing (to whoever has the fewest open conversations) "
     "— or unassign ('remove the assignee'). That's the whole assignment "
     "surface; there's no skill- or availability-based routing."),
    (("trigger", "when can", "fire", "run on", "start"),
     "A rule fires on exactly one trigger: "
     + "; ".join(schema.TRIGGER_LABELS.values()) + "."),
    (("condition", "filter", "match on", "criteria", "field"),
     "Conditions can look at the envelope (From/To/Cc/Bcc/Reply-To addresses "
     "and their domains), the content (Subject or Body keywords — contains, "
     "exact, or does-not-contain), the conversation's current state (tags, "
     "assignee, status) — those only on reply and state-change triggers, "
     "since a brand-new conversation has none yet — the day it arrived, or "
     "an AI-extracted variable. Groups combine with AND; alternatives inside "
     "a group with OR."),
    (("tag",),
     "Tags work two ways: as an ACTION a rule can add or remove them, and as "
     "a CONDITION it can match the tags a conversation already carries (is "
     "any of / is all of / is none of) — the condition only on reply and "
     "state-change triggers. Tags must already exist in the workspace; a rule "
     "can't create one."),
    (("status", "close", "pending", "reopen"),
     "A rule can set the conversation status to open, pending, or close. One "
     "status action per rule — if two are listed, only the last sticks."),
    (("note",),
     "Notes: a rule can add an internal note (optionally pinned), and the "
     "note text can reference AI-extracted variables like {{order_date}} so "
     "each conversation gets its own values filled in."),
    (("reply", "send", "respond", "auto-respond", "notification", "notify"),
     "Two outbound moves: send a reply on the conversation, and send the "
     "team a notification (in-app, optionally email too). Reply content is "
     "a template you describe."),
    (("inbox", "shared mailbox", "move"),
     "Shared-inbox moves: add the conversation to another shared inbox or "
     "remove it from this one. There's also a trigger for when a "
     "conversation is moved into the inbox."),
    (("ai", "detect", "classif", "extract", "summar"),
     "AI variables: a rule can ask AI to decide or extract something per "
     "conversation (is this a refund request? what's the order date?), gate "
     "its conditions on the result, and reference the values in notes. One "
     "variable per fact; booleans for yes/no gates, labels when you name "
     "the set."),
    (("integrat", "connector", "salesforce", "hubspot", "clickup", "custom field",
      "custom object", "approval", "sla", "webhook", "api"),
     None),  # composed by _integration_answer() below, scoped to the app(s) named
]


def _integration_answer(t):
    """The "integrat" topic's answer, scoped to whichever real app(s) the
    topic names — a live test found the OLD static text always opening with
    "Salesforce integration splits into two things..." even for a question
    that only ever named ClickUp, which read as flatly wrong (and buried the
    one real ClickUp capability the question was actually about three
    sentences later). Same "answer only from schema.py" discipline as the
    rest of this file; the only thing that changed is WHICH schema entries
    get read, using the exact same app-detection `relevant_capabilities()`
    already does, so the prose and the badges are never scoped differently
    from each other."""
    named_apps = [a for a in _KNOWN_APPS if _kw_match(t, (a,))]
    apps_to_cover = named_apps or list(_KNOWN_APPS)

    def _disp(app):
        return _APP_DISPLAY_NAMES.get(app, app.title())

    # a proper lead-in, not a mid-thought launch into "App features..." — a
    # live test called the answer "random" without one, and correctly so.
    lead = (f"{_disp(apps_to_cover[0])} integration covers what's live today:"
           if len(apps_to_cover) == 1
           else "Integrations cover what's live today, across every app connected here:")
    parts = [lead]
    feats = [f for f in apps_schema.FEATURES.values() if f["app"] in apps_to_cover]
    if feats:
        parts.append(
            "App features an admin enables once per workspace — no trigger, "
            "no per-conversation automation, just config: " + "; ".join(
                f"{f['name']} ({_disp(f['app'])}) — {f['description']}"
                + (f' e.g. "{f["example_phrasings"][0]}"' if f.get("example_phrasings") else "")
                for f in feats) + ".")

    natives = [n for n in schema.NATIVE_ACTIONS.values() if n["app"] in apps_to_cover]
    recipes = [r for r in schema.RECIPES.values() if r["app"] in apps_to_cover]
    b_parts = []
    if natives:
        b_parts.append("a built-in action Hiver already supports — " + "; ".join(
            f"{n['name']} ({_disp(n['app'])}) — {n['description'].rstrip('.')}"
            for n in natives))
    if recipes:
        b_parts.append("; ".join(
            f"a ready-made recipe — {r['name']} — {r['description'].rstrip('.')}"
            for r in recipes))
    if "salesforce" in apps_to_cover:
        b_parts.append(
            "I can also compose a Salesforce lookup on the fly for other asks that fit "
            "the same shape — look up data about the sender's Account/Contact/"
            "Opportunity/Case, then assign or tag the conversation based on it (e.g. "
            "assign to the Account Owner instead of the CSM, or tag by a Case's "
            "priority) — verified with a real test run before it counts as done, "
            "never just assumed to work")
    if b_parts:
        parts.append("Automations that react as conversations come in: "
                     + "; ".join(b_parts) + ".")

    # the UNSUPPORTED list is shared, app-agnostic vocabulary (custom fields,
    # approval flows, SLA policies aren't tied to one app) — kept in every
    # scoped answer. Its one entry that DOES namedrop a mechanism
    # (connector_other's "...a hand-vetted Salesforce recipe, a native app
    # action, or a Salesforce lookup...") reads as a non-sequitur when
    # Salesforce was never in view for this answer at all, so it's
    # generalized here rather than always quoting Salesforce specifically.
    unsupported_items = []
    for key, desc in schema.UNSUPPORTED.items():
        if key == "connector_other" and "salesforce" not in apps_to_cover:
            desc = "connector or app-action automations beyond what's built here"
        unsupported_items.append(desc)
    parts.append("Everything else here isn't yet: " + "; ".join(unsupported_items)
                 + ". I'll always say so rather than fake one of these.")
    return " ".join(parts)


def answer(topic):
    """Compose a capability answer for the classified topic. Returns prose,
    or the overview when the topic doesn't route anywhere specific."""
    t = re.sub(r"\s+", " ", str(topic or "")).strip().lower()
    if not t:
        return _OVERVIEW
    if _kw_match(t, _INTEGRATION_KEYS):
        return _integration_answer(t)
    for keys, text in _TOPICS:
        if text is not None and _kw_match(t, keys):
            return text
    return _OVERVIEW


# keywords for the ONE topic that names discrete, badge-able capabilities —
# same list _TOPICS' own "integrat" entry routes on. Every other topic
# (assignment, triggers, conditions, tags, statuses, notes, AI variables) is
# a generic rule-building PRIMITIVE, not a catalogued FEATURES/RECIPES/
# NATIVE_ACTIONS entry with its own id — there is nothing honest to badge
# there, so relevant_capabilities() returns [] for those on purpose rather
# than inventing a badge.
_INTEGRATION_KEYS = ("integrat", "connector", "salesforce", "hubspot", "clickup",
                    "custom field", "custom object", "approval", "sla", "webhook", "api")
_KNOWN_APPS = ("salesforce", "clickup")
# display casing for prose ("ClickUp", not "clickup".title() == "Clickup") —
# same small local override apps/setup.py's own APP_DISPLAY_NAMES uses, kept
# here rather than imported to avoid pulling apps.setup's clickup_mock/
# salesforce_mock/connected_apps/workspace imports into a pure prose module.
_APP_DISPLAY_NAMES = {"salesforce": "Salesforce", "clickup": "ClickUp"}


def relevant_capabilities(topic):
    """Structured capability badges for a capability-question topic — the
    same 'answer only from schema.py, never invent' discipline as answer()
    itself, just structured (id/name/app/kind) instead of prose, so a UI can
    render real, clickable capability chips instead of (or alongside) a
    misleading 'this turn built a rule' card for what was actually just a
    question. A live test asked for exactly this: asking about ClickUp's
    capabilities got a RuleCard with an 'excluded' question in it, instead
    of anything naming the real capabilities that answer the question.

    Scoped to whichever real app(s) the topic names (e.g. "clickup
    integration" -> only ClickUp's entries); no app named -> every app's
    entries, same as answer()'s own "integrat" text covering all of them."""
    t = re.sub(r"\s+", " ", str(topic or "")).strip().lower()
    if not _kw_match(t, _INTEGRATION_KEYS):
        return []
    named_apps = [a for a in _KNOWN_APPS if _kw_match(t, (a,))]

    def _matches(app):
        return not named_apps or app in named_apps

    badges = []
    for fid, f in apps_schema.FEATURES.items():
        if _matches(f["app"]):
            badges.append({"id": fid, "name": f["name"], "app": f["app"], "kind": "app_feature"})
    for rid, r in schema.RECIPES.items():
        if _matches(r["app"]):
            badges.append({"id": rid, "name": r["name"], "app": r["app"], "kind": "recipe"})
    for nid, n in schema.NATIVE_ACTIONS.items():
        if _matches(n["app"]):
            badges.append({"id": nid, "name": n["name"], "app": n["app"], "kind": "native_action"})
    return badges
