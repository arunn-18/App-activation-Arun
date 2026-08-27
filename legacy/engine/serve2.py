#!/usr/bin/env python3
"""ARCHIVED (2026-08-27, App Activation charter): see legacy/engine/
serve_api.py's own note — same reasoning, this is the older plain-text UI
for the general (non-app-scoped) Automations panel. Kept for reference,
not run from this location; add engine/ to sys.path to run it again.

v2 copilot chat UI (schema + validator engine).

Run:  ../../automation-copilot/.venv/bin/python serve2.py   ->  http://127.0.0.1:8001
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import connected_apps
import copilot
import router
import workspace as wsmod

CLIENT = router.make_client()
WS = wsmod.load()  # demo fixture; comment out to run workspace-less like the eval
# connected-apps fixture: same one serve_apps.py (the Apps-panel entry) uses,
# so a connector rule built from EITHER panel gets the same prerequisite
# check and the same test-run — one engine behind both entry points.
APPS_WS = connected_apps.load()

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Automation Copilot v2 — schema+validator</title>
<style>
 body{font-family:-apple-system,sans-serif;max-width:760px;margin:0 auto;padding:16px;
      background:#111;color:#eee}
 h3{color:#8ab4f8} .msg{padding:10px 14px;border-radius:10px;margin:8px 0;white-space:pre-wrap}
 .you{background:#2b5cd9;margin-left:20%} .bot{background:#222;margin-right:10%;
      font-family:ui-monospace,monospace;font-size:13px}
 form{display:flex;gap:8px;margin-top:12px}
 input{flex:1;padding:10px;border-radius:8px;border:1px solid #444;background:#1a1a1a;color:#eee}
 button{padding:10px 16px;border-radius:8px;border:0;background:#2b5cd9;color:#fff;cursor:pointer}
 .hint{color:#888;font-size:12px}
</style></head><body>
<h3>Automation Copilot v2 <span class="hint">— structured spec + code validator (port 8001)</span></h3>
<div id="log"></div>
<form onsubmit="send(event)"><input id="q" autofocus placeholder="e.g. apply tag when conversation comes">
<button>Send</button></form>
<p class="hint">The validator plans the questions; the model only extracts. Values it can't
trace to your own words are dropped and re-asked.</p>
<script>
let messages=[];
function add(cls,text){const d=document.createElement('div');d.className='msg '+cls;
 d.textContent=text;document.getElementById('log').appendChild(d);d.scrollIntoView();}
async function send(e){e.preventDefault();const q=document.getElementById('q');
 const text=q.value.trim();if(!text)return;q.value='';add('you',text);
 messages.push({role:'user',content:text});
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({messages})});
 const j=await r.json();const reply=j.reply||('ERROR: '+j.error);
 add('bot',reply);messages.push({role:'assistant',content:reply});}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self._send(200, PAGE, "text/html; charset=utf-8")
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/chat":
            return self._send(404, '{"error":"not found"}')
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            msgs = [m for m in req.get("messages", []) if m.get("role") in ("user", "assistant")]
            reply = copilot.respond(CLIENT, msgs, ws=WS, apps_ws=APPS_WS)
            # the ```json null``` block is machine plumbing for the eval CLI — not for humans
            reply = reply.replace("```json\nnull\n```", "").rstrip()
            self._send(200, json.dumps({"reply": reply}))
        except Exception as e:
            self._send(200, json.dumps({"error": str(e)[:300]}))


if __name__ == "__main__":
    port = 8001
    print(f"Automation Copilot v2 → http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
