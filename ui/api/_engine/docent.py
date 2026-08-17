"""Capability answers, from code — never from the model.

Mid-build, users ask what the builder can do ("apart from round robin is there
any other assignment that i can do?"). The extraction model only CLASSIFIES the
question (capability_question topic string); the answer is composed here from
schema.py, so every capability named is one the engine can actually build, and
what's out of scope is stated from the UNSUPPORTED list rather than omitted or
invented. Question turns are read-only: the draft rule is not touched.

Lane line: automation vocabulary only (triggers, conditions, actions, AI
variables, limits). Anything else gets an honest redirect.
"""
import re

import schema

_OVERVIEW = (
    "Here's the surface I can build on: a rule fires on one trigger (new "
    "inbound/outbound conversations, incoming replies, outgoing email, or a "
    "conversation moved into the inbox), filters on conditions (sender/"
    "recipient addresses and domains, subject and body keywords, the "
    "conversation's current tags/assignee/status, day received, or an "
    "AI-extracted variable), then runs actions — tag or "
    "untag, assign (one person or round-robin), set status, add a note, send "
    "a reply or notification, add to or remove from a shared inbox, or (one "
    "recipe so far) run a connector automation. Ask about "
    "any of these and I'll go deeper."
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
     "One connector recipe is supported so far: " + next(iter(schema.RECIPES.values()))["name"]
     + " — " + next(iter(schema.RECIPES.values()))["description"] + " Everything else here "
     "isn't yet: " + "; ".join(schema.UNSUPPORTED.values())
     + ". I'll always say so rather than fake one of these."),
]


def answer(topic):
    """Compose a capability answer for the classified topic. Returns prose,
    or the overview when the topic doesn't route anywhere specific."""
    t = re.sub(r"\s+", " ", str(topic or "")).strip().lower()
    if not t:
        return _OVERVIEW
    for keys, text in _TOPICS:
        if any(k in t for k in keys):
            return text
    return _OVERVIEW
