"""POST /api/preview — dry-run a final rule JSON over the mailbox fixture
(Vercel Python function). Same contract as engine/serve_api.py's /api/preview:
pure code, no LLM — blast radius before the rule exists.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_engine"))
import preview  # noqa: E402

MAILBOX = preview.load_mailbox()


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
            rule = req.get("rule")
            if not isinstance(rule, dict) or not rule.get("trigger"):
                return self._send(400, {"error": "rule (final JSON) required"})
            return self._send(200, preview.preview(rule, MAILBOX))
        except Exception as e:  # surface, don't crash
            return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
