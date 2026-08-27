"""GET /api/workspace — the demo workspace fixture (Vercel Python function)."""
import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "_engine"))
import workspace as wsmod  # noqa: E402

WS = wsmod.load()


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(WS, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
