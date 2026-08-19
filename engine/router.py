"""The FIRST model call of every turn: decide which track this conversation
is in — BEFORE either track's schema is even loaded. This is the fix for
the "still works with the automation schema" bug: previously, one shared
extraction call filled automation fields (trigger/actions) AND had two
bolted-on Track A fields (app_feature/feature_setup) squeezed in beside
them — so downstream code, and the wire format itself, never stopped
looking like "an automation, plus an afterthought." Now automation/extract.py
and apps/extract.py are two independent, peer schemas that don't know about
each other; this module is the ONLY place that decides which one runs.

Classification only — this module NEVER fills in a trigger, an action, a
feature, or a setup slot. copilot.py calls automation.extract.extract() when
track == "automation", or apps.extract.extract() when track == "app_setup".

`track` reflects what the CONVERSATION AS A WHOLE is about, not just the
latest message — once established, it stays that way across turns (the
model re-derives it fresh each turn from the whole history, exactly like
condition_groups accumulate for automations) unless the user clearly pivots
to the other track. `capability_question` and `no_intent` are READ-ONLY
classifications that can be set ALONGSIDE a track (mirroring the old
single-call design): a capability question or a gibberish message doesn't
erase whatever automation/app-setup progress the conversation already has —
the track-specific extractor still runs afterward and re-renders it
unchanged, same as before this split.
"""
import json
from pathlib import Path

from apps import schema as apps_schema

MODEL = "gpt-4o"


def _vocab_block():
    lines = ["APP FEATURES (Track A — the COMPLETE list of 'app_setup' asks; anything "
             "else that isn't per-conversation automation but doesn't match one of "
             "these is NOT app_setup either — see the disambiguation rule below):"]
    for fid, f in apps_schema.FEATURES.items():
        lines.append(f"  {fid} ({f['app']}) — {f['description']}")
    return "\n".join(lines)


SYSTEM = f"""You are the FIRST step of a two-step pipeline for a Hiver automation/app-setup
copilot. Your ONLY job is to classify what kind of turn this conversation is — you
do NOT fill in any trigger, condition, action, feature, or setup detail; a separate
specialized extractor does that next, using ONLY the `track` you choose. Output ONLY
the JSON classification.

{_vocab_block()}

TRACKS:
- "automation": the user wants a rule that fires PER CONVERSATION — "when X happens,
  do Y" (a trigger + conditions + actions), including connector automations (e.g.
  auto-assigning conversations to the Salesforce account's CSM). This is the default
  track for anything automation-shaped, EVEN WHEN it turns out to be unbuildable —
  route it here anyway and let the automation extractor name the gap; do not decide
  buildability yourself.
- "app_setup": the user wants to turn on / configure an EXISTING app capability that
  is NOT per-conversation — nothing fires "when X happens, do Y". Matches ONLY the
  APP FEATURES list above.

DISAMBIGUATION (the easy mistake — a real test showed "set up Salesforce account
cards for my shared mailbox" misclassified as an automation/connector ask):
  - VIEWING / SHOWING / DISPLAYING existing information alongside a conversation —
    "account cards", "contact details", "see the customer's info", "show me their
    Salesforce record" — is app_setup. There is no "when X, do Y" shape.
  - CREATING, PUSHING, SYNCING, or ASSIGNING data per conversation — "log this email
    in Salesforce", "create a case", "sync conversations", "assign to the CSM
    automatically" — is automation, even if it mentions the same app.
  - An app-setup-sounding ask that doesn't match any APP FEATURES entry (wrong app,
    or a real idea not built yet) is NOT app_setup either — track it as "automation"
    anyway (the automation extractor's unsupported/unmappable handling names the gap
    honestly); never invent a feature id to force a match.

RULES:
1. track reflects the CONVERSATION AS A WHOLE, re-derived fresh every turn from the
   entire history — once established (this turn or any earlier one), it stays that
   way unless the user clearly pivots to the other track. Never flip tracks just
   because the latest message alone looks ambiguous in isolation.
2. When nothing is established yet AND the current message doesn't clearly establish
   one either (e.g. a bare capability question on turn 1), default track to
   "automation" — harmless, since the automation extractor will simply find nothing
   to fill.
3. capability_question: ONLY when the LATEST user message is a QUESTION about what
   the builder/app-setup can do ("what other assignment options are there?", "can
   this show custom fields too?"), not a request to build or configure anything. Set
   it to a SHORT topic phrase echoing their words; otherwise null. A message that
   ANSWERS a question, names entities, picks an option, or states a value is NOT a
   capability question, even if it mentions a capability. This is a READ-ONLY
   classification — it does not change `track`, and the track-specific extractor
   still runs afterward so any existing progress renders unchanged.
4. no_intent: a SHORT reason when the LATEST user message has NO automation or
   app-setup content at all — a keysmash or gibberish ("sdfdsfdsfsd"), small talk, or
   a remark unrelated to building/configuring anything. null otherwise. Never set it
   for a message that answers a question, names a value, wraps up, or asks what the
   builder can do. Also READ-ONLY — does not change `track`.
5. intent_summary: ONE sentence, second person, restating what the user is trying to
   ACHIEVE in your own words. "auto-close everything from notifications@streamliner.
   example" -> "You want the Streamliner notification emails closed automatically so
   nobody has to deal with them." "set up Salesforce account cards" -> "You want to
   see Salesforce account and contact details on conversations." Never start with an
   imperative verb copied from the request.
"""

RESPONSE_SCHEMA = {
    "name": "track_classification",
    "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "intent_summary": {"type": "string"},
            "track": {"type": "string", "enum": ["automation", "app_setup"]},
            "capability_question": {"type": ["string", "null"]},
            "no_intent": {"type": ["string", "null"]},
        },
        "required": ["intent_summary", "track", "capability_question", "no_intent"],
    },
}


def load_env():
    env = {}
    env_file = Path(__file__).parent.parent.parent / "automation-copilot" / ".env"
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.split("#")[0].strip()
    except OSError:
        pass  # not on the dev machine (e.g. deployed) — env var must be set
    return env


def make_client():
    import os
    from openai import OpenAI
    key = os.environ.get("OPENAI_API_KEY") or load_env().get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set (env var or v1 .env file)")
    return OpenAI(api_key=key)


def classify(client, messages, model=MODEL):
    """messages: [{role, content}] chat history. Returns
    {intent_summary, track, capability_question, no_intent}."""
    msgs = [{"role": "system", "content": SYSTEM}] + messages
    resp = client.chat.completions.create(
        model=model, temperature=0, max_tokens=300,
        response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
        messages=msgs)
    try:
        return json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError:
        resp = client.chat.completions.create(
            model=model, temperature=0.2, max_tokens=300,
            response_format={"type": "json_schema", "json_schema": RESPONSE_SCHEMA},
            messages=msgs)
        return json.loads(resp.choices[0].message.content)
