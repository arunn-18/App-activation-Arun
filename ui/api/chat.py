"""POST /api/chat — one copilot turn (Vercel Python function).

Same contract as engine/serve_api.py's /api/chat. No SSE here — Vercel's
Python handler buffers responses, and the UI's stream client already falls
back to this endpoint, degrading gracefully to a single Working step.
Requires OPENAI_API_KEY in the environment.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# the deployed demo runs in pilot scope — no AI, no integrations, no time
# conditions — so behaviour matches what the UI footer promises
os.environ.setdefault("COPILOT_PILOT_SCOPE", "1")

sys.path.insert(0, str(Path(__file__).parent / "_engine"))
import connected_apps  # noqa: E402
import copilot  # noqa: E402
import router  # noqa: E402
import workspace as wsmod  # noqa: E402

WS = wsmod.load()
# connected-apps fixture (v2.8): lets a connector rule's prerequisites get
# checked and its recipe test-run from this deployed demo too, same as the
# local serve_api.py / serve2.py entry points.
APPS_WS = connected_apps.load()
_client = None


def client():
    global _client
    if _client is None:
        _client = router.make_client()
    return _client


class handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            msgs = [{"role": m["role"], "content": str(m["content"])}
                    for m in req.get("messages", [])
                    if m.get("role") in ("user", "assistant") and m.get("content")]
            if not msgs or msgs[-1]["role"] != "user":
                return self._send(400, {"error": "messages must end with a user turn"})
            return self._send(200, copilot.respond_structured(client(), msgs, ws=WS,
                                                              apps_ws=APPS_WS))
        except Exception as e:  # surface, don't crash
            return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
