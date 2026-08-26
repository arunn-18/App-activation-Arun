#!/usr/bin/env python3
"""Apps-panel entry point — scoped to ONE connected app at a time.

The product requirement this exists for: an admin configures an app-based
automation from EITHER the Apps panel or the Automations panel, because it's
the exact same underlying flow either way. So this file is deliberately thin:
it imports the SAME schema.py / extract.py / validator.py / copilot.py /
executor.py the Automations panel (serve2.py / serve_api.py) uses — no
forked engine, no copy of the recipe/validation/execution logic. The only
thing this entry point adds is scoping by app and offering BOTH tracks for
that one app:
  - Track A: enable an existing App feature (features.py) — no automation,
             Apps-panel-only, no Automations-panel equivalent.
  - Track B: build/run a connector automation recipe (schema.RECIPES) via
             the same chat pipeline serve2.py uses.

Run:  ../../automation-copilot/.venv/bin/python serve_apps.py  -> http://127.0.0.1:8011

Endpoints:
  GET  /api/apps                    every app in the connected-apps fixture,
                                    with its connection state
  GET  /api/apps/<app>              that app's Track A features + Track B
                                    recipes, each flagged buildable/blocked
                                    against its prerequisites
  POST /api/apps/<app>/features/<feature_id>/enable
                                    Track A: features.resolve_setup() from a
                                    clean start (see the /chat endpoint for
                                    the real multi-turn flow)
  POST /api/apps/<app>/chat         Track B: {"messages":[...]} ->
                                    copilot.respond_structured(), scoped to
                                    this app — see the SCOPING note below
  GET  /api/apps/<app>/testable-conversations
                                    capability 7's conversation picker —
                                    real mailbox conversations to test a
                                    view feature's preview or a write
                                    feature's create-form against
  POST /api/apps/<app>/features/<feature_id>/test-create
                                    capability 7 for a WRITE feature:
                                    {"feature": <the completed feature dict>,
                                    "field_values": {label: value}} -> a
                                    real (mock) created record — see
                                    copilot.test_create_feature()

SCOPING NOTE: /chat now threads `app` into copilot.respond_structured() ->
automation_extract.extract(), which scopes CONNECTOR RECIPES/NATIVE APP
ACTIONS (and the custom_plan SALESFORCE OBJECTS line) to just this app —
see automation/extract.py's _vocab_block() docstring. This was flagged as a
"no-op until a second app exists" TODO when there was only one recipe
(Salesforce); ClickUp's native action is what proved the filter's shape.
validator.py's recipe/native-action lookup is NOT separately scoped — the
vocab filter above already keeps extraction from proposing an out-of-scope
id in the first place, so there's nothing for the validator to catch that
this doesn't already prevent.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import connected_apps
import copilot
import mailbox_lookup
import router
import workspace as wsmod
from apps import setup as features
from automation import schema

CLIENT = router.make_client()
APPS_WS = connected_apps.load()
WS = wsmod.load()

APP_PATH = re.compile(r"^/api/apps/([^/]+)$")
FEATURE_ENABLE_PATH = re.compile(r"^/api/apps/([^/]+)/features/([^/]+)/enable$")
CHAT_PATH = re.compile(r"^/api/apps/([^/]+)/chat$")
TEST_CREATE_PATH = re.compile(r"^/api/apps/([^/]+)/features/([^/]+)/test-create$")
TESTABLE_CONVERSATIONS_PATH = re.compile(r"^/api/apps/([^/]+)/testable-conversations$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # CORS open to localhost dev servers — same as serve_api.py. Missing
        # this meant a browser-based UI (the whole point of this endpoint)
        # could never actually reach it: the request would just fail with a
        # CORS error, not a visible API error, before this fix.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        # split off the query string ONCE — only the testable-conversations
        # route below reads one (capability 7's mailbox picker, 2026-08-26);
        # every other route keeps matching on the bare path exactly as
        # before, since none of them ever carried a query string.
        path, _, query = self.path.partition("?")
        if path == "/api/apps":
            return self._send(200, {"apps": list(APPS_WS.get("connected_apps", {}))})
        m = APP_PATH.match(path)
        if m:
            app = m.group(1)
            # copy each entry rather than mutate schema.FEATURES/RECIPES in
            # place — those are shared module-level dicts, not per-request
            # state, and every other consumer (extract.py's vocab block,
            # validator.py's recipe lookup) reads them directly.
            feats = {fid: {**f, "_blocked_on": connected_apps.prerequisites_met(
                          APPS_WS, app, f["prerequisites"])}
                    for fid, f in features.list_features(app).items()}
            recipes = {rid: {**r, "_blocked_on": connected_apps.prerequisites_met(
                             APPS_WS, app, r["prerequisites"])}
                      for rid, r in schema.RECIPES.items() if r["app"] == app}
            # native actions (capability 5) — a genuinely separate listing from
            # recipes: no chain, pre-built by Hiver. ClickUp only has this one,
            # which is exactly why it needed its own key rather than being
            # folded into track_b_recipes.
            natives = {nid: {**n, "_blocked_on": connected_apps.prerequisites_met(
                             APPS_WS, app, n["prerequisites"])}
                      for nid, n in schema.NATIVE_ACTIONS.items() if n["app"] == app}
            return self._send(200, {
                "app": app,
                "connected": connected_apps.is_connected(APPS_WS, app),
                "track_a_features": feats,
                "track_b_recipes": recipes,
                "native_actions": natives,
            })
        m = TESTABLE_CONVERSATIONS_PATH.match(path)
        if m:
            # capability 7's conversation picker — shown BEFORE the
            # write-test-create form (or a view feature's preview), never
            # skipped straight past. `?inbox=` (optional, 2026-08-26): the
            # mailbox picker step ahead of this one scopes the list to ONE
            # of the feature's own enabled inbox(es) — see FeatureCard.tsx's
            # WriteTestForm. Contact-matching (require_contact_match) is
            # Salesforce-only: ClickUp's write feature has no contact
            # concept, so every conversation in scope is testable there —
            # see mailbox_lookup.testable_conversations()'s own docstring.
            app = m.group(1)
            inbox = parse_qs(query).get("inbox", [None])[0]
            return self._send(200, {"conversations": mailbox_lookup.testable_conversations(
                inboxes=[inbox] if inbox else None,
                require_contact_match=(app == "salesforce"))})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        m = FEATURE_ENABLE_PATH.match(self.path)
        if m:
            # Track A is a multi-turn setup (auth -> objects -> fields ->
            # enable-for-inboxes), not a single-shot toggle — this REST
            # shortcut just reports the first blocking question from a clean
            # start; the real flow is the /chat endpoint below, which
            # accumulates feature_setup across turns the same way copilot.py
            # does.
            _, feature_id = m.groups()
            return self._send(200, features.resolve_setup(feature_id, {}, APPS_WS, WS))
        m = TEST_CREATE_PATH.match(self.path)
        if m:
            # capability 7's write-feature test (see copilot.test_create_
            # feature's own docstring) — a real form submission, not a chat
            # turn: the client sends back the completed `feature` dict it
            # already has plus the values typed into the test form.
            try:
                length = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(length) or b"{}")
                feature = req.get("feature")
                field_values = req.get("field_values") or {}
                if not isinstance(feature, dict):
                    return self._send(400, {"error": "feature (the completed feature dict) required"})
                return self._send(200, copilot.test_create_feature(feature, field_values, APPS_WS))
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
        m = CHAT_PATH.match(self.path)
        if m:
            app = m.group(1)
            try:
                length = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(length) or b"{}")
                msgs = [{"role": mm["role"], "content": str(mm["content"])}
                        for mm in req.get("messages", [])
                        if mm.get("role") in ("user", "assistant") and mm.get("content")]
                if not msgs or msgs[-1]["role"] != "user":
                    return self._send(400, {"error": "messages must end with a user turn"})
                # WS is threaded through for Track A's enable-for-inboxes step
                # (apps.setup.resolve_setup) — Track B's connector recipe still
                # has no entity (tag/user/inbox) slots of its own to resolve,
                # only test_contact_email, which needs provenance, not lookup.
                # `app` scopes automation_extract's connector vocab to just
                # this app (see automation/extract.py's _vocab_block()) — no
                # longer a no-op now that a second app (ClickUp) exists to
                # prove the filter's shape against.
                state = copilot.respond_structured(CLIENT, msgs, ws=WS, apps_ws=APPS_WS, app=app)
                state["app"] = app
                return self._send(200, state)
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    print("Apps-panel entry -> http://127.0.0.1:8011  "
         "(GET /api/apps, GET /api/apps/<app>, POST /api/apps/<app>/chat, "
         "GET /api/apps/<app>/testable-conversations, "
         "POST /api/apps/<app>/features/<id>/enable, "
         "POST /api/apps/<app>/features/<id>/test-create)")
    ThreadingHTTPServer(("127.0.0.1", 8011), Handler).serve_forever()
