"""Eval CLI: stdin -> stdout. No workspace by default (keeps the core/ai/mt runs
comparable); pass --workspace to load the fixture (the entity-resolution slice).

Two input shapes:
  plain text                     one user turn, one reply (the original contract)
  {"turns": ["...", "..."]}      scripted multi-turn: each user turn is appended to
                                 the history, the copilot replies in between, and the
                                 FULL transcript is printed. report.py grades the last
                                 fenced JSON block (the final rule, or null).

Used by:  run_eval.py --engine command --cmd "<venv-python> cli.py [--workspace] [--apps-workspace]"

--apps-workspace (v2.8): loads connected_apps.json so connector-recipe
prerequisites get checked (needed for eval/connector-eval-set.jsonl); off by
default so every other eval set's behavior is unaffected.
"""
import json
import sys

import connected_apps
import copilot
import router
import workspace as wsmod

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    client = router.make_client()
    ws = wsmod.load() if "--workspace" in sys.argv else None
    apps_ws = connected_apps.load() if "--apps-workspace" in sys.argv else None
    if raw.startswith("{"):
        turns = json.loads(raw)["turns"]
        msgs, out = [], []
        for i, turn in enumerate(turns, 1):
            msgs.append({"role": "user", "content": turn})
            reply = copilot.respond(client, msgs, ws=ws, apps_ws=apps_ws)
            msgs.append({"role": "assistant", "content": reply})
            out.append(f"--- user[{i}]: {turn}\n--- copilot[{i}]:\n{reply}")
        print("\n\n".join(out))
    else:
        print(copilot.respond(client, [{"role": "user", "content": raw}], ws=ws,
                              apps_ws=apps_ws))
