"""LLM extraction: conversation -> partial AUTOMATION rule spec (structured
output). Runs ONLY when router.classify() has already decided this turn's
track is "automation" — this module has no concept of Track A at all (no
app_feature, no feature_setup); that vocabulary lives entirely in
apps/extract.py, a genuine peer of this file, not a shared schema this one
also has to know about.

The model's ONLY job is faithful slot-filling: map the user's words onto the legal
vocabulary, leave unknowns null/empty, list unsupported asks. It never decides
what to ask or whether the rule is complete — that's automation/validator.py's job.
capability_question/no_intent classification already happened in router.py before
this was even called.
"""
import json

import workspace as wsmod

from . import schema

MODEL = "gpt-4o"

def _vocab_block():
    lines = ["TRIGGERS:"]
    for t, desc in schema.TRIGGERS.items():
        lines.append(f"  {t} — {desc}")
    lines.append("CONDITION PROPERTIES (property: allowed operators):")
    for p, s in schema.CONDITION_PROPERTIES.items():
        extra = f" values={s['values']}" if s.get("values") else ""
        lines.append(f"  {p}: {', '.join(s['ops'])}{extra}")
    lines.append("AI VARIABLE TYPES (for ai_extract): " + ", ".join(schema.AI_VARIABLE_TYPES))
    lines.append("ACTIONS (type: params — leave a param null/[] if the user did not give it):")
    for a, s in schema.ACTIONS.items():
        params = []
        for pname, pspec in s["params"].items():
            params.append(f"{pname}" + (f"={'|'.join(pspec['enum'])}"
                                        if pspec.get("enum") else ""))
        lines.append(f"  {a}: {', '.join(params)}")
    lines.append("CONNECTOR RECIPES (legal values for the 'connector' action's `recipe` "
                 "param — this is the COMPLETE list; nothing else exists, however plausible "
                 "it sounds):")
    for rid, r in schema.RECIPES.items():
        lines.append(f"  {rid} ({r['app']}) — {r['description']}")
    lines.append("UNSUPPORTED (recognize, put in unsupported_requests, never emit as actions): "
                 + "; ".join(f"{k} ({v})" for k, v in schema.UNSUPPORTED.items()))
    return "\n".join(lines)


SYSTEM = f"""You extract Hiver AUTOMATION rule specs from a conversation (router.py has
already decided this turn is about an automation, not an app-feature setup). Output
ONLY the JSON spec.

{_vocab_block()}

EXTRACTION RULES:
1. Fill a slot ONLY with information present in the USER's messages. If the user has not
   named a tag / person / status / keyword / inbox, leave that slot null or []. NEVER
   invent values, NEVER borrow them from these instructions, and NEVER write
   placeholder text into a slot ("inbox_name_here", "tag_to_be_decided") — null means
   not provided, and that is the correct output.
2. condition_groups semantics: groups are AND'd; conditions inside a group are OR'd; a
   condition's values array means "any of these". Therefore when the user joins
   requirements with OR ("sender is X, or the subject is Y"), those conditions go in the
   SAME group: [[from is X, subject is Y]]. When they join with AND ("from X and about
   Y"), each goes in its OWN group: [[from X], [subject Y]]. "subject or body mentions
   X" = one group with two conditions, each carrying ALL the keywords. When a LATER
   message answers how conditions relate — "either one is enough" / "any of them" =
   alternatives, merge into ONE group; "both must match" / "all of them" = keep
   separate groups.
3. scope_confirmed = true ONLY if the user explicitly said all/every/everything, or gave at
   least one condition. Bare plurals ("incoming emails") do NOT confirm scope.
4. Trigger mapping: "when an email comes in / we receive" and "each/every new
   incoming email" -> new_conversation_inbound; new_email_incoming_from_* is ONLY
   for replies arriving on existing threads; "when we send" -> new_email_outgoing. DEFAULT: when the request is about emails/conversations with no
   explicit reply/outgoing context ("emails from acme.com", "tag Patrick's emails"),
   use new_conversation_inbound — the assumption is surfaced to the user later, so do
   NOT leave trigger null just because the user never said "when". Null only when there
   is no email context at all.
4b. "unassign" / "remove the assignee" -> action assign with target "UNASSIGN".
5. unsupported_requests is ONLY for capabilities in the UNSUPPORTED list (connectors,
   custom fields...). An ask that maps to a supported action but lacks its value
   ("tag it appropriately", "route it to the right person") is that ACTION with
   empty/null params — never unsupported, never dropped.
6. Copy user values verbatim (exact spelling/casing of tags, names, keywords,
   addresses). A quoted string is ONE value — never split it on '/', commas, or
   internal 'or' ("body contains 'CME/CE/CEU Certificate'" is a single value).
7. Mechanism answers are not values: "match on specific senders" / "by subject keywords"
   says HOW to match, not what — create the condition but leave its values [] until the
   user gives the actual senders/keywords.
8. Operator choice: default to 'contains' for address and text matching — to/cc/bcc/
   reply_to headers can hold several addresses, so "addressed to X" or "CC'd to X" is
   ALWAYS 'contains', never 'is'. The SAME default applies to from/from_domain:
   "emails from x@y.com" -> from contains x@y.com. Use 'is' only when the user says
   exactly/precisely ("from exactly a@b.com", "the exact subject 'Z'").
9. AI variables (ai_extract): when the user asks to detect / classify / judge /
   summarize / draft / extract something that literal keyword or address matching
   cannot do ("use AI to spot billing emails", "have AI pull out the order date"),
   define variables in ai_extract. One variable per fact — create a variable for
   EVERY fact the user asks the AI to determine, note, or extract, even when no
   condition or action ends up referencing it ("also noting whether it uses
   urgent wording" = its own boolean). One CHECK over several alternatives is
   still ONE fact: "whether it's about X, Y, or Z" = ONE boolean covering all
   three, never one boolean per alternative. If the user names a
   variable (e.g. "request_type"), keep their name verbatim; otherwise derive a
   short snake_case name from their words. Types: DEFAULT to boolean — any
   decision that gates whether the actions run is a yes/no boolean, even when the
   user describes the two sides at length ("decide if it's a routine reminder
   (close it) versus an overdue notice (leave it alone)" = ONE boolean like
   close_email). Use single_select ONLY when the user wants a label recorded or
   used across several actions AND names the label set; options = the user's own
   labels VERBATIM (their casing and wording, never snake_cased, never invented).
   date/time/number/email only when the extracted value is clearly that; else
   text. Write each variable's description as clear instructions to the AI, from
   the user's wording. Do NOT create AI variables when a literal condition
   suffices ("sender contains stripe.com" is a from condition, not AI), and do
   NOT create one just because the request contains a fuzzy adjective
   ("important client emails", "interesting leads") when the user never asked
   for AI — leave conditions empty and let the scope question collect the
   literal criteria. If a later answer supplies literal criteria (senders,
   domains, keywords), those REPLACE any provisional AI detection of the same
   intent — drop the AI variable, don't AND them together.
10. Gating on AI results: when the actions should only run for positive
   detections, add a condition {{property: "ai_variable", variable: <name>,
   op: "is", values: ["true"]}} for booleans (["false"] when the user wants the
   negative case). EVERY gate the user states must become a condition — declaring
   the variable is not enough. Gates that must ALL hold are AND'd, so EACH goes in
   its OWN group: "on Closed conversations, when AI says it's an acknowledgment
   and found no action items" = three groups: [[status is close]],
   [[ai acknowledgment is true]], [[ai action_items does_not_exist]]. Never put an
   AI gate in the same group as a status/keyword condition unless the user said
   "or". For single_select, gate on the label(s) the user named ("when it's
   CRITICAL or HIGH" -> two conditions in the SAME group, one per label). When the
   user asks AI to list/extract things and the actions require none were found,
   gate that variable with does_not_exist (exists for "only when one was found").
   "If/when the extraction found something" IS a gate — "if either variable is
   present, add a note" means CREATE the exists conditions: ai_extract A and B +
   one group [[A exists, B exists]] ("either" = OR = same group). Such a gate
   also confirms scope. "Keep it Closed" / "set the status back to X" is an
   explicit status action, even when the status looks unchanged.
   A pure extract-and-note rule ("extract X and note it down" with no detection
   gate) has NO ai condition.
11. Note templates: reference AI variables inside add_note content as
   {{{{name}}}} ("pin a note with the urgency and reason" -> content mentioning
   {{{{urgency_level}}}} and {{{{urgency_reason}}}}). Only reference declared
   variables.
12. The 'variable' field on a condition: REQUIRED (the AI variable's name) on every
   condition whose property is "ai_variable" — including exists/does_not_exist
   gates — and null on every other property.
13. closing = true ONLY when the LATEST user message adds no rule content and just
   wraps up: acknowledges, thanks, or confirms they're done ("that's about it",
   "no, all good", "looks good, thanks", "we're done"). A message that answers a
   question, adds/changes any value, or asks for an adjustment is closing = false,
   even if it also says thanks ("use the Urgent tag, thanks!" -> false).
14. intent_summary: ONE sentence, second person, restating what the user is trying
   to ACHIEVE in your own words — it is shown to them as proof you understood.
   Surface the implicit goal, don't echo their phrasing or dump the rule. "auto-
   close everything from notifications@streamliner.example" -> "You want the
   Streamliner notification emails closed automatically so nobody has to deal
   with them." NEVER start with an imperative verb copied from the request.
16. unmappable: when a requirement CANNOT be expressed in the vocabulary above —
   no condition property matches it, no action does — record it here as
   {{request: <the user's own words>, why: <what is missing>}} and leave the rule
   without it. NEVER bend such a request into a different property to make it
   fit ("has tag VIP" is NOT status is VIP) — a wrong condition that looks legal
   is far worse than a declared gap, because the user cannot see it is wrong.
17. State conditions (tag / assignee / status) describe the conversation as it
   ALREADY IS, so they exist ONLY on reply and state-change triggers, never on
   the new-conversation ones. "a follow-up on a conversation tagged VIP" =
   trigger new_email_incoming_from_anyone (or the mailbox-reply/contact-reply
   variant if the user says who replied) + condition tag is_any_of ['VIP'].
   This OVERRIDES rule 4's new_conversation_inbound default: when the user
   filters on an existing tag, assignee or status, the trigger must be a reply
   or state-change trigger. Use the tag/assignee/status conditions — they are
   real; do not put them in unmappable.
19. Connector recipes: the 'connector' action's `recipe` param is legal ONLY as
   one of the CONNECTOR RECIPES ids listed above. There is currently exactly
   ONE recipe — match it ONLY when the request clearly wants what its
   description says (assigning/routing conversations to a Salesforce
   Account's CSM). Do not get creative because little else is defined: a
   request for ANY other connector/integration/CRM action — a different
   Salesforce action, HubSpot, ClickUp, a generic "call our API", a webhook —
   is NOT this recipe. For those, add "connector_other" reasoning to
   unsupported_requests (never invent a fake recipe id, never leave `recipe`
   null hoping the code will ask — with one recipe there is nothing to ask,
   only a match or a clean escalation). test_contact_email is filled ONLY
   from an email address the user actually wrote, exactly like any other
   provenance-guarded value (rule 1).
"""

RESPONSE_SCHEMA = {
    "name": "automation_spec",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "intent_summary": {"type": "string"},
            "trigger": {"type": ["string", "null"], "enum": list(schema.TRIGGERS) + [None]},
            "scope_confirmed": {"type": "boolean"},
            "condition_groups": {
                "type": "array",
                "items": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "property": {"type": "string",
                                     "enum": list(schema.CONDITION_PROPERTIES)},
                        "op": {"type": "string"},
                        "values": {"type": "array", "items": {"type": "string"}},
                        "variable": {"type": ["string", "null"]},
                    },
                    "required": ["property", "op", "values", "variable"],
                }},
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": list(schema.ACTIONS)},
                        "tags": {"type": ["array", "null"], "items": {"type": "string"}},
                        "target": {"type": ["string", "null"]},
                        "targets": {"type": ["array", "null"], "items": {"type": "string"}},
                        "status_value": {"type": ["string", "null"],
                                         "enum": schema.STATUS_VALUES + [None]},
                        "distribution": {"type": ["string", "null"],
                                         "enum": schema.DISTRIBUTION_METHODS + [None]},
                        "content": {"type": ["string", "null"]},
                        "pinned": {"type": ["boolean", "null"]},
                        "email_enabled": {"type": ["boolean", "null"]},
                        "inbox": {"type": ["string", "null"]},
                        "body_hint": {"type": ["string", "null"]},
                        "recipe": {"type": ["string", "null"],
                                  "enum": list(schema.RECIPES) + [None]},
                        "test_contact_email": {"type": ["string", "null"]},
                    },
                    "required": ["type", "tags", "target", "targets", "status_value",
                                 "distribution", "content", "pinned",
                                 "email_enabled", "inbox", "body_hint",
                                 "recipe", "test_contact_email"],
                },
            },
            "ai_extract": {
                "type": ["object", "null"], "additionalProperties": False,
                "properties": {
                    "variables": {
                        "type": "array",
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string",
                                         "enum": schema.AI_VARIABLE_TYPES},
                                "description": {"type": "string"},
                                "options": {"type": "array",
                                            "items": {"type": "string"}},
                            },
                            "required": ["name", "type", "description", "options"],
                        },
                    },
                },
                "required": ["variables"],
            },
            "unsupported_requests": {"type": "array", "items": {"type": "string"}},
            "closing": {"type": "boolean"},
            "unmappable": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False,
                          "properties": {"request": {"type": "string"},
                                         "why": {"type": "string"}},
                          "required": ["request", "why"]},
            },
        },
        "required": ["intent_summary", "trigger", "scope_confirmed",
                     "condition_groups", "actions", "ai_extract",
                     "unsupported_requests", "closing", "unmappable"],
    },
}


# Appended to SYSTEM only when a workspace is connected, so the eval path
# (no workspace) keeps a byte-identical prompt and stays comparable.
WORKSPACE_RULES = """
W. A workspace is connected: its tags, agents, and shared inboxes are real. BEFORE
   filling tags / target / targets / inbox slots, resolve what the user named with
   the tools (list_tags, find_user, list_inboxes):
   - exactly one plausible match -> fill the slot with the CANONICAL name from the
     tool result (user says "sarah", find_user returns only Sarah Lee -> "Sarah Lee";
     "the events inbox" + list_inboxes shows Events -> inbox "Events").
   - several matches, or none -> fill the slot with the user's OWN words verbatim
     ("john"). NEVER pick one, and NEVER leave the slot null when the user named
     someone/something — the user's words must reach the slot so the right
     follow-up question can be asked.
   - never fill a slot with an entity the user did not refer to.
   Rule 1 still applies: the user's words are the only source of WHICH entity;
   the workspace only supplies its exact spelling."""

MAX_TOOL_ROUNDS = 5


def build_system(ws=None):
    return SYSTEM + WORKSPACE_RULES if ws else SYSTEM


def extract(client, messages, model=MODEL, ws=None, on_event=None):
    """messages: [{role, content}] chat history. Returns the parsed spec dict.
    With a workspace, runs a bounded tool-calling loop before the final spec.
    on_event (optional): called with progress dicts as real pipeline steps happen
    (currently one per workspace tool call) — the honest feed for UI progress."""
    msgs = [{"role": "system", "content": build_system(ws)}] + messages
    kwargs = dict(model=model, temperature=0, max_tokens=2000,
                  response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA})
    if ws:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(messages=msgs, tools=wsmod.TOOLS,
                                                  **kwargs)
            m = resp.choices[0].message
            if not m.tool_calls:
                return json.loads(m.content)
            msgs.append({"role": "assistant", "content": m.content,
                         "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
            for tc in m.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                if on_event:
                    on_event({"stage": "lookup", "tool": tc.function.name,
                              "query": args.get("name", "")})
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "content": wsmod.dispatch(ws, tc.function.name, args)})
        # tool budget exhausted: force a final spec without tools
    resp = client.chat.completions.create(messages=msgs, **kwargs)
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        # rare runaway/truncated generation: one rescue attempt with a nudge
        kwargs["temperature"] = 0.2
        resp = client.chat.completions.create(messages=msgs, **kwargs)
        return json.loads(resp.choices[0].message.content)
