#!/usr/bin/env python3
"""Structured JSON API for the copilot — the surface a real UI builds on.

Run:  ../../automation-copilot/.venv/bin/python serve_api.py   ->  http://127.0.0.1:8010

Endpoints (CORS open to localhost dev servers):
  GET  /api/workspace            the demo workspace fixture (tags, agents, inboxes)
  POST /api/chat                 {"messages":[{role,content},...]}
                                 -> copilot.respond_structured() dict:
                                    status, spec, rule, draft, questions,
                                    resolutions, entity_notes, unsupported, errors
  POST /api/chat/stream          same request; SSE-style stream of REAL pipeline
                                 events as they happen —
                                   data: {"type":"progress","stage":"extracting"}
                                   data: {"type":"progress","stage":"lookup",...}
                                   data: {"type":"progress","stage":"validating"}
                                   data: {"type":"result", ...TurnState}

The chat UI for humans stays at serve2.py (port 8001); this server returns machine
state so a frontend can render the draft, questions, and final rule as components.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import os

# the served demo runs in pilot scope (no AI, no integrations, no time
# conditions) so behaviour matches what the UI footer promises. Eval runs go
# through cli.py and keep the full capability.
os.environ.setdefault("COPILOT_PILOT_SCOPE", "1")

import copilot
import extract
import preview
import schema
import workspace as wsmod

CLIENT = extract.make_client()
WS = wsmod.load()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        if self.path == "/api/workspace":
            return self._send(200, WS)
        if self.path == "/api/vocabulary":
            # builder-vocabulary labels for UIs — single source, can't drift
            return self._send(200, {"triggers": schema.TRIGGER_LABELS,
                                    "properties": schema.PROPERTY_LABELS})
        return self._send(404, {"error": "not found"})

    def _read_messages(self):
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        msgs = [{"role": m["role"], "content": str(m["content"])}
                for m in req.get("messages", [])
                if m.get("role") in ("user", "assistant") and m.get("content")]
        if not msgs or msgs[-1]["role"] != "user":
            return None
        return msgs

    def do_POST(self):
        if self.path == "/api/chat":
            try:
                msgs = self._read_messages()
                if msgs is None:
                    return self._send(400, {"error": "messages must end with a user turn"})
                return self._send(200, copilot.respond_structured(CLIENT, msgs, ws=WS))
            except Exception as e:  # surface, don't crash the server
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
        if self.path == "/api/chat/stream":
            return self._stream_chat()
        if self.path == "/api/preview":
            # dry-run a FINAL rule JSON over the mailbox fixture — pure code,
            # no LLM; blast radius before the rule exists
            try:
                length = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(length) or b"{}")
                rule = req.get("rule")
                if not isinstance(rule, dict) or not rule.get("trigger"):
                    return self._send(400, {"error": "rule (final JSON) required"})
                return self._send(200, preview.preview(rule))
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {str(e)[:300]}"})
        return self._send(404, {"error": "not found"})

    def _stream_chat(self):
        try:
            msgs = self._read_messages()
        except Exception as e:
            return self._send(400, {"error": str(e)[:200]})
        if msgs is None:
            return self._send(400, {"error": "messages must end with a user turn"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def emit(obj):
            self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        try:
            emit({"type": "progress", "stage": "extracting"})
            state = copilot.respond_structured(
                CLIENT, msgs, ws=WS,
                on_event=lambda e: emit({"type": "progress", **e}))
            emit({"type": "result", **state})
        except Exception as e:
            emit({"type": "error", "error": f"{type(e).__name__}: {str(e)[:300]}"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print("copilot API -> http://127.0.0.1:8010  (GET /api/workspace, POST /api/chat)")
    ThreadingHTTPServer(("127.0.0.1", 8010), Handler).serve_forever()
