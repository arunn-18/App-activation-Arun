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
                                    this app (today: a no-op scope, since
                                    there is exactly one recipe total — see
                                    the SCOPING note below)

SCOPING NOTE (shaped by having seen only one app/recipe): with exactly one
recipe, and it belonging to Salesforce, "scoped to this app" is automatically
true — there is nothing else to filter out. When recipe #2 lands for a
DIFFERENT app, thread an `app` filter into extract.build_system()'s vocab
block (schema.RECIPES.items() filtered by app) and into validator's recipe
lookup here, so this endpoint only ever offers/accepts recipes for its own
app. Do not build that filtering machinery now against a single data point —
there's no second example yet to prove the filter's shape against.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import connected_apps
import copilot
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/apps":
            return self._send(200, {"apps": list(APPS_WS.get("connected_apps", {}))})
        m = APP_PATH.match(self.path)
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
            return self._send(200, {
                "app": app,
                "connected": connected_apps.is_connected(APPS_WS, app),
                "track_a_features": feats,
                "track_b_recipes": recipes,
            })
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
                state = copilot.respond_structured(CLIENT, msgs, ws=WS, apps_ws=APPS_WS)
                state["app"] = app  # scoping is a no-op today (see module docstring)
                return self._send(200, state)
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    print("Apps-panel entry -> http://127.0.0.1:8011  "
         "(GET /api/apps, GET /api/apps/<app>, POST /api/apps/<app>/chat, "
         "POST /api/apps/<app>/features/<id>/enable)")
    ThreadingHTTPServer(("127.0.0.1", 8011), Handler).serve_forever()
