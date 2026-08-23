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

import salesforce_schema
import workspace as wsmod

from . import planner
from . import schema

MODEL = "gpt-4o"

def _vocab_block(app=None):
    """`app` (optional): when given (the Apps-panel entry point, scoped to
    one connected app — see serve_apps.py's own SCOPING NOTE, which flagged
    this as a TODO before there was a second app to prove it against),
    CONNECTOR RECIPES and NATIVE APP ACTIONS list ONLY that app's entries —
    a live test with two real apps (Salesforce, ClickUp) showed the
    unfiltered vocab as noise that made it easier for the model to
    misclassify which app a bare request was even about. `app=None` (the
    general Automations copilot, "/") keeps the full unscoped list — that
    surface legitimately builds automations for any app, or none at all."""
    lines = ["TRIGGERS:"]
    for t, desc in schema.TRIGGERS.items():
        lines.append(f"  {t} — {desc}")
    lines.append("CONDITION PROPERTIES (property: allowed operators):")
    for p, s in schema.CONDITION_PROPERTIES.items():
        extra = f" values={s['values']}" if s.get("values") else ""
        lines.append(f"  {p}: {', '.join(s['ops'])}{extra}")
    lines.append("AI VARIABLE TYPES (for ai_extract): " + ", ".join(schema.AI_VARIABLE_TYPES))
    # scoped BEFORE the ACTIONS loop below, which also needs these two sets —
    # the connector action's own `recipe`/`native_action_id` "legal values"
    # line is generated generically from schema.ACTIONS[...]["params"][...]
    # ["enum"] (the full, unscoped list schema.py declares); a live test
    # caught that leak: CONNECTOR RECIPES/NATIVE APP ACTIONS further down
    # were correctly scoped, but this earlier line still advertised every
    # app's recipe/native-action id regardless, undermining the scoping.
    recipes = {rid: r for rid, r in schema.RECIPES.items() if app is None or r["app"] == app}
    natives = {nid: n for nid, n in schema.NATIVE_ACTIONS.items()
              if app is None or n["app"] == app}
    lines.append("ACTIONS (type: params — leave a param null/[] if the user did not give it):")
    for a, s in schema.ACTIONS.items():
        params = []
        for pname, pspec in s["params"].items():
            # `recipe`'s enum is schema.py's full unscoped list; native_
            # action_id isn't in this params dict at all (it's declared only
            # in RESPONSE_SCHEMA below) so no equivalent leak exists for it.
            enum = list(recipes) or None if pname == "recipe" else pspec.get("enum")
            params.append(f"{pname}" + (f"={'|'.join(enum)}" if enum else ""))
        lines.append(f"  {a}: {', '.join(params)}")
    lines.append("CONNECTOR RECIPES (legal values for the 'connector' action's `recipe` "
                 "param — this is the COMPLETE list; nothing else exists, however plausible "
                 "it sounds):")
    for rid, r in recipes.items():
        lines.append(f"  {rid} ({r['app']}) — {r['description']}")
    lines.append("NATIVE APP ACTIONS (legal values for the 'connector' action's "
                 "`native_action_id` param — a pre-built Hiver action block, not an API "
                 "call this engine composes; this is the COMPLETE list):")
    for nid, n in natives.items():
        lines.append(f"  {nid} ({n['app']}) — {n['description']}")
    # custom_plan only ever targets Salesforce (schema.py's own "app" enum) —
    # irrelevant noise when scoped to a different app entirely.
    if app is None or app == "salesforce":
        lines.append("SALESFORCE OBJECTS available for a connector's custom_plan (see rule 19b) — "
                     "call describe_object on one before referencing its fields, never guess a "
                     "field name: " + ", ".join(sorted(salesforce_schema.OBJECTS)))
    lines.append("UNSUPPORTED (recognize, put in unsupported_requests, never emit as actions): "
                 + "; ".join(f"{k} ({v})" for k, v in schema.UNSUPPORTED.items()))
    return "\n".join(lines)


_SYSTEM_TEMPLATE = """You extract Hiver AUTOMATION rule specs from a conversation (router.py has
already decided this turn is about an automation, not an app-feature setup). Output
ONLY the JSON spec.

{vocab}

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
   request for a DIFFERENT Salesforce action this recipe doesn't cover (see
   rule 19b before giving up on it) is not this recipe; a request matching a
   NATIVE APP ACTION instead (rule 19a) is not this recipe either.
   test_contact_email is filled ONLY from an email address the user actually
   wrote, exactly like any other provenance-guarded value (rule 1).
19a. Native app actions: the 'connector' action's `native_action_id` param is
   legal ONLY as one of the NATIVE APP ACTIONS ids listed above — match it
   when the request wants EXACTLY what that action's description says
   ("create a ClickUp task from this conversation" -> clickup_create_task).
   Check this BEFORE attempting a custom_plan (rule 19b): a native action is
   Hiver's own pre-built block, simpler and more certain than composing API
   calls, so prefer it whenever one actually matches. target_name (which
   list/board/channel — provenance-guarded, rule 1) and title_hint (what the
   created item should be titled/about — free text, not provenance-guarded,
   same as add_note's content) are its own two slots; leave either null if
   the user hasn't said it yet. recipe/native_action_id/custom_plan are all
   mutually exclusive — never fill more than one on the same action. A
   request for a NON-Salesforce, non-native-action integration (a generic
   "call our API" against an app with no NATIVE APP ACTIONS entry, a
   webhook) is NOT buildable at all — add "connector_other" reasoning to
   unsupported_requests for those (never invent a fake id, never leave
   every connector field null hoping the code will ask — with this little
   vocabulary there is nothing to ask, only a match or a clean escalation).
19b. Dynamic connector plans (custom_plan): when a Salesforce-connector-shaped
   ask does NOT match the one CONNECTOR RECIPES entry or any NATIVE APP
   ACTION, but IS a "look up some Salesforce data about this account/contact,
   then assign or tag the conversation based on it" request (e.g. "assign new
   conversations to the Account Owner instead of the CSM", "tag it with the
   Case's priority when there's an open case"), attempt to compose a
   custom_plan INSTEAD of escalating to unsupported_requests:
   - Call describe_object (and list_objects if you need to see what exists
     first) to learn REAL field names before writing a step — never guess one.
   - steps: an ORDERED list of {{object, where, extract_variables}} lookups,
     each `where` clause filtering by a field that either came from a PRIOR
     step's extract_variables or is the seed `contact_email` (the sender's
     address is always available as {{{{contact_email}}}} for the first
     step's Contact lookup, exactly like the recipe above). Every `field` you
     reference — in `where` or `extract_variables` — must be one
     describe_object actually returned for that object. Maximum 4 steps.
   - terminal: exactly one of {{kind: "assign", target: "{{{{var}}}}"}} or
     {{kind: "add_tag", tags: ["{{{{var}}}}"]}}, where `{{{{var}}}}` is a
     variable an EARLIER step's extract_variables produced — never a literal
     value, never a field you haven't actually extracted.
   - plan_summary: ONE plain-English sentence describing what the plan does,
     for the admin to read (they will never see the raw steps by default).
   - If no plausible chain of real objects/fields gets from the seed contact
     to a sensible assign/tag source, do NOT force one — leave custom_plan
     null and use "connector_other" in unsupported_requests instead, exactly
     like rule 19's clean escalation. A wrong plan that merely LOOKS
     plausible is far worse than an honestly declared gap.
   - recipe, native_action_id, and custom_plan are mutually exclusive: never
     fill more than one on the same action.
"""


def _system_text(app=None):
    return _SYSTEM_TEMPLATE.format(vocab=_vocab_block(app))


# unscoped default — the general Automations copilot ("/", serve_api.py/
# serve2.py) always extracts against this; nothing about switching
# _vocab_block()/SYSTEM from a bare f-string to this function changes what
# it produces for app=None (see the "exactly one single-brace expression"
# check this refactor was verified against before landing).
SYSTEM = _system_text()

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
                        # Native app action (rule 19a) — Hiver's own pre-built
                        # action block, the mechanism to prefer over custom_plan
                        # when one actually matches. target_name/title_hint are
                        # its two generic slots (see NATIVE_ACTIONS' own comment
                        # in schema.py for why they're named this generically).
                        "native_action_id": {"type": ["string", "null"],
                                            "enum": list(schema.NATIVE_ACTIONS) + [None]},
                        "target_name": {"type": ["string", "null"]},
                        "title_hint": {"type": ["string", "null"]},
                        # A dynamically-composed connector plan (rule 19b) — the
                        # OTHER way to fill a connector action when no RECIPES
                        # entry or native action matches. extract_variables is an array of
                        # {variable, field} pairs, not a {name: field} map:
                        # strict-mode JSON schema can't express an
                        # arbitrary-key object, only fixed-shape ones (see
                        # plan_validator.py, which converts this wire shape
                        # into the dict run_chain() actually uses).
                        "custom_plan": {
                            "type": ["object", "null"], "additionalProperties": False,
                            "properties": {
                                "app": {"type": "string", "enum": ["salesforce"]},
                                "plan_summary": {"type": "string"},
                                "steps": {
                                    "type": "array",
                                    "items": {
                                        "type": "object", "additionalProperties": False,
                                        "properties": {
                                            "object": {"type": "string",
                                                      "enum": list(salesforce_schema.OBJECTS)},
                                            "where": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "additionalProperties": False,
                                                    "properties": {
                                                        "field": {"type": "string"},
                                                        "eq": {"type": "string"},
                                                    },
                                                    "required": ["field", "eq"],
                                                },
                                            },
                                            "extract_variables": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "additionalProperties": False,
                                                    "properties": {
                                                        "variable": {"type": "string"},
                                                        "field": {"type": "string"},
                                                    },
                                                    "required": ["variable", "field"],
                                                },
                                            },
                                        },
                                        "required": ["object", "where", "extract_variables"],
                                    },
                                },
                                "terminal": {
                                    "type": "object", "additionalProperties": False,
                                    "properties": {
                                        "kind": {"type": "string",
                                                "enum": ["assign", "add_tag"]},
                                        "target": {"type": ["string", "null"]},
                                        "tags": {"type": ["array", "null"],
                                                "items": {"type": "string"}},
                                    },
                                    "required": ["kind", "target", "tags"],
                                },
                            },
                            "required": ["app", "plan_summary", "steps", "terminal"],
                        },
                    },
                    "required": ["type", "tags", "target", "targets", "status_value",
                                 "distribution", "content", "pinned",
                                 "email_enabled", "inbox", "body_hint",
                                 "recipe", "test_contact_email", "native_action_id",
                                 "target_name", "title_hint", "custom_plan"],
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


def build_system(ws=None, app=None):
    text = _system_text(app)
    return text + WORKSPACE_RULES if ws else text


_PLANNER_TOOL_NAMES = {t["function"]["name"] for t in planner.TOOLS}


def extract(client, messages, model=MODEL, ws=None, on_event=None, app=None):
    """messages: [{role, content}] chat history. Returns the parsed spec dict.
    Runs a bounded tool-calling loop before the final spec: planner.TOOLS
    (list_objects/describe_object) are ALWAYS available, so a connector ask
    can be explored into a custom_plan (rule 19b) whether or not a workspace
    is connected — those tools describe Salesforce's own schema, not
    workspace entities, so they don't depend on ws the way wsmod.TOOLS does.
    wsmod.TOOLS are added on top when ws is supplied, exactly as before.
    on_event (optional): called with progress dicts as real pipeline steps
    happen (one per tool call) — the honest feed for UI progress.
    app (optional): scopes CONNECTOR RECIPES/NATIVE APP ACTIONS vocab to
    just this app (see _vocab_block's own docstring) — set by the Apps
    panel, left None everywhere else."""
    msgs = [{"role": "system", "content": build_system(ws, app)}] + messages
    kwargs = dict(model=model, temperature=0, max_tokens=2000,
                  response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA})
    tools = list(planner.TOOLS) + (list(wsmod.TOOLS) if ws else [])
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(messages=msgs, tools=tools, **kwargs)
        m = resp.choices[0].message
        if not m.tool_calls:
            return json.loads(m.content)
        msgs.append({"role": "assistant", "content": m.content,
                     "tool_calls": [tc.model_dump() for tc in m.tool_calls]})
        for tc in m.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            if on_event:
                on_event({"stage": "lookup", "tool": tc.function.name,
                          "query": args.get("name") or args.get("object_name", "")})
            if tc.function.name in _PLANNER_TOOL_NAMES:
                content = planner.dispatch(tc.function.name, args)
            else:
                content = wsmod.dispatch(ws, tc.function.name, args)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": content})
    # tool budget exhausted: force a final spec without tools
    resp = client.chat.completions.create(messages=msgs, **kwargs)
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        # rare runaway/truncated generation: one rescue attempt with a nudge
        kwargs["temperature"] = 0.2
        resp = client.chat.completions.create(messages=msgs, **kwargs)
        return json.loads(resp.choices[0].message.content)
