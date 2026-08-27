"""LLM extraction: conversation -> partial Track A SETUP spec (structured
output). Runs ONLY when router.classify() has already decided this turn's
track is "app_setup" — this module has no concept of triggers, conditions,
or actions at all; that vocabulary lives entirely in automation/extract.py,
a genuine peer of this file. Which feature this ask is about was already
narrowed to "app_setup" by the router (using the same FEATURES list); this
extractor's job is picking WHICH feature and filling its setup slots.

The model's ONLY job is faithful slot-filling: map the user's words onto the
legal vocabulary (feature ids, object names, field names — all fixed enums
from apps/schema.py, never free text), leave unknowns null/empty. It never
decides what to ask next or whether setup is complete — that's
apps/setup.py's resolve_setup() job.
"""
import json

from . import schema

MODEL = "gpt-4o"


def _vocab_block():
    lines = ["APP FEATURES (the COMPLETE list of legal `feature` values):"]
    for fid, f in schema.FEATURES.items():
        lines.append(f"  {fid} ({f['app']}) — {f['description']}")
        if f.get("object_choices"):
            lines.append(f"    setup: pick records from {f['object_choices']} (`objects`), "
                         "then pick fields per record (`<object>_fields`) — see rule 3.")
    lines.append("FIELD CATALOG (legal values for `account_fields` / `contact_fields` — "
                 "standard AND custom; nothing outside these lists is real):")
    for obj, cat in schema.FIELD_CATALOG.items():
        lines.append(f"  {obj}: standard={cat['standard']}, custom={cat['custom']}")
    # clickup_create_task_from_hiver (capability 4's second app) has no VIEW
    # feature/catalog at all — its only legal field vocab is the write-usecase
    # one, so it needs its own listing rather than reusing FIELD_CATALOG above.
    lines.append("TASK FIELD CATALOG (legal values for `task_fields` — "
                 "standard AND custom; nothing outside these lists is real):")
    for obj, cat in schema.CLICKUP_WRITABLE_FIELD_CATALOG.items():
        lines.append(f"  {obj}: standard={cat['standard']}, custom={cat['custom']}")
    return "\n".join(lines)


SYSTEM = f"""You extract Track A APP-FEATURE SETUP specs from a conversation (router.py has
already decided this turn is about configuring an existing app feature, not an
automation). Output ONLY the JSON spec.

{_vocab_block()}

EXTRACTION RULES:
1. feature: the APP FEATURES id this conversation is about, re-derived every turn
   from the WHOLE history (once established, keep it — the router already confirmed
   this conversation is app_setup, so there should always be a match). Leave null
   ONLY if genuinely no APP FEATURES entry matches (a real Track A idea not built
   yet, or the wrong app) — record that in `unmappable`, never invent a feature id
   to force a match.
2. connect_requested: true the moment the user agrees to connect the app (answers
   "yes"/"connect" to a connect prompt, or says "connect salesforce" unprompted).
   Keep it true for the rest of the conversation once said.
3. objects: every record type the user named THAT IS in the matched feature's
   object_choices (e.g. "Account", "Contact") — legal values ONLY from the APP
   FEATURES setup line above, never invented, never a record type from a different
   feature.
4. account_fields / contact_fields / task_fields: every field name the user picked
   for that object, legal values ONLY from the FIELD CATALOG / TASK FIELD CATALOG
   above for that object (standard or custom — both are real, don't treat custom
   fields as less legitimate). A later message REMOVING a field ("actually, drop
   phone number") changes the CURRENT list — re-derive the accumulated set from the
   whole conversation, don't just append.
5. inboxes: every shared inbox the user names when asked which inbox(es) this
   feature should be enabled for — capture their own words for the name(s)
   verbatim (e.g. "Support", "the billing inbox"); the code matches them against
   the real workspace list, so you don't need to know it. Naming an inbox here
   IS the enable action — there is no separate yes/no confirmation. A later
   message REMOVING one ("actually not Billing") changes the CURRENT list —
   re-derive the accumulated set from the whole conversation, don't just append.
   Leave any slot null/[] the user hasn't addressed — the code (not you) decides
   what to ask next and in what order.
6. closing = true ONLY when the LATEST user message adds no setup content and just
   wraps up: acknowledges, thanks, or confirms they're done. A message that answers
   a setup question or adds/changes any value is closing = false, even if it also
   says thanks.
7. intent_summary: ONE sentence, second person, restating what the user is trying
   to ACHIEVE. "set up Salesforce account cards" -> "You want to see Salesforce
   account and contact details on conversations."
7b. test_contact_email: filled ONLY from a real email address the user actually
   wrote — same provenance rule as any other free-text value — when they name
   one to preview this against ("test it with jordan@acme.example", or picking
   one of the real conversations offered). This is a COURTESY once the feature
   is otherwise fully set up, never required for completeness; leave it null
   until the user actually names one.
8. unmappable: when the ask genuinely doesn't match any APP FEATURES entry despite
   being an app-setup-shaped request — record {{request: <user's own words>,
   why: <what is missing>}}, leave `feature` null. Never bend a mismatched ask into
   the nearest feature to make it fit. Never record a bare capability QUESTION
   here either ("what can this show?") — capability_question (classified
   separately, upstream) already covers it; unmappable is for a real setup ask
   with no matching feature, not a meta-question with nothing to configure.
9. feature_request_requested: true the moment the user agrees to log an unmappable
   ask as a feature request (answers "yes"/"log it"/"please" to the copilot's own
   offer, or says so unprompted); false the moment they explicitly decline ("no
   thanks", "don't bother", "no"). This is a courtesy, not part of the feature
   setup itself — never let it affect feature/objects/fields/inboxes/unmappable in
   any way. Leave null until the user actually answers either way; once answered
   (true OR false), keep that answer for the rest of the conversation — don't keep
   re-asking after a "no".
10. prefill_requested / prefill_fields (clickup_create_task_from_hiver only, once
   the feature is otherwise fully set up): true the moment the user names an
   actual field + default value to prefill ("default the Priority to High"), or
   says an unambiguous yes ("sure, set some defaults"); false the moment they
   decline ("skip", "no thanks", "not now"). prefill_fields: {{field, value}}
   pairs the user actually named — legal `field` values ONLY from the ones
   already chosen for this feature's own write form (task_fields), never
   invented, never a field this feature isn't exposing. Optional courtesy, never
   part of the feature itself — leave prefill_requested null until answered
   either way, then keep that answer for the rest of the conversation.
11. quick_access_enabled (clickup_create_task_from_hiver only, same "otherwise
   fully set up" timing as rule 10): true the moment the user agrees to enable
   Quick Access (a task badge on the conversation for easy access back to a
   created task) — "yes", "enable it", "turn it on"; false the moment they
   decline ("skip", "no", "not now"). Optional courtesy, never part of the
   feature itself. Leave null until answered either way, then keep that answer
   for the rest of the conversation.
"""

RESPONSE_SCHEMA = {
    "name": "app_setup_spec",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "intent_summary": {"type": "string"},
            "feature": {"type": ["string", "null"], "enum": list(schema.FEATURES) + [None]},
            "connect_requested": {"type": ["boolean", "null"]},
            "objects": {"type": ["array", "null"], "items": {"type": "string"}},
            # Fixed shape, not a dynamic map: account_fields/contact_fields are
            # named for the two objects schema.FIELD_CATALOG currently covers —
            # a future object needs its own <object>_fields property added
            # here, the same way test_contact_email is the connector recipe's
            # one slot (see automation/schema.py's ACTIONS["connector"] comment
            # for the same point from the other track).
            "account_fields": {"type": ["array", "null"], "items": {"type": "string"}},
            "contact_fields": {"type": ["array", "null"], "items": {"type": "string"}},
            # clickup_create_task_from_hiver's own <object>_fields slot — same
            # fixed-shape reasoning as account_fields/contact_fields above.
            "task_fields": {"type": ["array", "null"], "items": {"type": "string"}},
            "inboxes": {"type": ["array", "null"], "items": {"type": "string"}},
            # "test on a real conversation" (capability 7, rule 7b) — a
            # courtesy once the feature is otherwise complete, never
            # required. Same shape/name as the connector recipe's own
            # test_contact_email (automation/schema.py's ACTIONS["connector"]).
            "test_contact_email": {"type": ["string", "null"]},
            "closing": {"type": "boolean"},
            "unmappable": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False,
                          "properties": {"request": {"type": "string"},
                                         "why": {"type": "string"}},
                          "required": ["request", "why"]},
            },
            # rule 9: the Discovery movement's "log this as a feature
            # request?" offer (Apps Activation PRD, 2026-08-24) — same
            # slot/meaning as automation/extract.py's own field.
            "feature_request_requested": {"type": ["boolean", "null"]},
            # rules 10/11 (2026-08-26): steps 5/6, ClickUp's write feature
            # only — see apps/setup.py's own step list. prefill_fields is an
            # array of {field, value} pairs, not a dynamic map, for the same
            # strict-JSON-schema reason automation/schema.py's custom_plan
            # extract_variables is (see that field's own comment).
            "prefill_requested": {"type": ["boolean", "null"]},
            "prefill_fields": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False,
                          "properties": {"field": {"type": "string"},
                                         "value": {"type": "string"}},
                          "required": ["field", "value"]},
            },
            "quick_access_enabled": {"type": ["boolean", "null"]},
        },
        "required": ["intent_summary", "feature", "connect_requested", "objects",
                     "account_fields", "contact_fields", "task_fields", "inboxes",
                     "test_contact_email", "closing", "unmappable",
                     "feature_request_requested", "prefill_requested",
                     "prefill_fields", "quick_access_enabled"],
    },
}


def extract(client, messages, model=MODEL):
    """messages: [{role, content}] chat history. Returns the parsed setup spec."""
    msgs = [{"role": "system", "content": SYSTEM}] + messages
    kwargs = dict(model=model, temperature=0, max_tokens=1000,
                  response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA})
    resp = client.chat.completions.create(messages=msgs, **kwargs)
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        # rare runaway/truncated generation: one rescue attempt with a nudge
        kwargs["temperature"] = 0.2
        resp = client.chat.completions.create(messages=msgs, **kwargs)
        return json.loads(resp.choices[0].message.content)
