"""Eval CLI: stdin -> stdout. No workspace by default (keeps the core/ai/mt runs
comparable); pass --workspace to load the fixture (the entity-resolution slice).

Two input shapes:
  plain text                     one user turn, one reply (the original contract)
  {"turns": ["...", "..."]}      scripted multi-turn: each user turn is appended to
                                 the history, the copilot replies in between, and the
                                 FULL transcript is printed. report.py grades the last
                                 fenced JSON block (the final rule, or null).

Used by:  run_eval.py --engine command --cmd "<venv-python> cli.py [--workspace]"
"""
import json
import sys

import copilot
import extract
import workspace as wsmod

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    client = extract.make_client()
    ws = wsmod.load() if "--workspace" in sys.argv else None
    if raw.startswith("{"):
        turns = json.loads(raw)["turns"]
        msgs, out = [], []
        for i, turn in enumerate(turns, 1):
            msgs.append({"role": "user", "content": turn})
            reply = copilot.respond(client, msgs, ws=ws)
            msgs.append({"role": "assistant", "content": reply})
            out.append(f"--- user[{i}]: {turn}\n--- copilot[{i}]:\n{reply}")
        print("\n\n".join(out))
    else:
        print(copilot.respond(client, [{"role": "user", "content": raw}], ws=ws))
