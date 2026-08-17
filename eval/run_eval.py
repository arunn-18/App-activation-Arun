"""Runner: send eval-set queries to an engine, capture raw responses to a run file.

Does NO grading — that's report.py, so grading can be rerun without re-paying API calls.

Engines:
  --engine echo     replay ideal_output as the answer (pipeline dry-run; report must score 100%)
  --engine command  pipe each query to a shell command's stdin, capture stdout
  --engine openai   system-prompt file + OpenAI chat completion (the v1 baseline path)

Examples:
  python3 run_eval.py --engine echo --scope core
  python3 run_eval.py --engine openai --scope core \
      --system-prompt ../../automation-copilot/testing/SYSTEM-PROMPT.md --model gpt-4o
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
EVAL_SET = HERE / "real-world-eval-set.jsonl"
RUNS_DIR = HERE / "runs"

# Appended to the user message for --engine openai, so a prose-first prompt (v1)
# still yields machine-parseable output. The flat shape matches the v1 golden-set
# vocabulary; grader.py converts it to canonical form.
JSON_SUFFIX = """

After your normal reply, ALSO output the rule as a fenced JSON code block in exactly this shape:
```json
{"trigger": "...", "conditions": [{"field": "...", "operator": "...", "value": "..."}], "logic": "AND|OR|null", "actions": [{"type": "...", "value": "..."}]}
```
Use `values` (array) instead of `value` when a condition matches any of several values. If you cannot or should not build a rule (out of scope, needs clarification), output ```json null ``` instead."""


def load_records(scope, eval_set=EVAL_SET):
    records = [json.loads(l) for l in open(eval_set)]
    if scope == "core":
        records = [r for r in records if not r["scope_flags"]]
    elif scope == "flagged":
        records = [r for r in records if r["scope_flags"]]
    elif scope != "all":
        records = [r for r in records if scope in r["scope_flags"]]
    return records


def engine_echo(record, _args):
    return json.dumps(record["ideal_output"], ensure_ascii=False)


def engine_command(record, args):
    # multi-turn records carry scripted user turns; the CLI plays them in order
    payload = (json.dumps({"turns": record["turns"]}, ensure_ascii=False)
               if record.get("turns") else record["user_query"])
    proc = subprocess.run(args.cmd, shell=True, input=payload,
                          capture_output=True, text=True, timeout=600)
    if not proc.stdout.strip() and proc.stderr.strip():
        raise RuntimeError("engine wrote no stdout; stderr tail: "
                           + proc.stderr.strip()[-400:])
    return proc.stdout


def engine_openai(record, args, _cache={}):
    from openai import OpenAI  # lazy import; needs OPENAI_API_KEY
    if "client" not in _cache:
        _cache["client"] = OpenAI()
        _cache["system"] = Path(args.system_prompt).read_text()
    resp = _cache["client"].chat.completions.create(
        model=args.model,
        temperature=args.temperature,
        messages=[{"role": "system", "content": _cache["system"]},
                  {"role": "user", "content": record["user_query"] + JSON_SUFFIX}],
    )
    return resp.choices[0].message.content


ENGINES = {"echo": engine_echo, "command": engine_command, "openai": engine_openai}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--engine", choices=ENGINES, required=True)
    p.add_argument("--scope", default="core",
                   help="core (no flags) | flagged | all | <flag name>")
    p.add_argument("--cmd", help="shell command for --engine command")
    p.add_argument("--model", default="gpt-4o")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--system-prompt", help="path to system prompt file (openai engine)")
    p.add_argument("--limit", type=int)
    p.add_argument("--out")
    p.add_argument("--run-name", default=None)
    p.add_argument("--eval-set", default=str(EVAL_SET),
                   help="eval set jsonl (default real-world-eval-set.jsonl)")
    args = p.parse_args()

    if args.engine == "openai" and not args.system_prompt:
        sys.exit("--engine openai requires --system-prompt")
    if args.engine == "command" and not args.cmd:
        sys.exit("--engine command requires --cmd")

    records = load_records(args.scope, args.eval_set)
    if args.limit:
        records = records[: args.limit]

    prompt_sha = ""
    if args.system_prompt:
        prompt_sha = hashlib.sha256(Path(args.system_prompt).read_bytes()).hexdigest()[:12]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = args.run_name or f"{ts}-{args.engine}-{args.scope}"
    out_path = Path(args.out) if args.out else RUNS_DIR / f"{name}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    engine_fn = ENGINES[args.engine]
    meta = {"engine": args.engine, "model": args.model if args.engine == "openai" else None,
            "temperature": args.temperature if args.engine == "openai" else None,
            "prompt_sha": prompt_sha, "scope": args.scope, "started": ts,
            "eval_set": Path(args.eval_set).name, "eval_set_records": len(records)}

    with open(out_path, "w") as f:
        f.write(json.dumps({"_meta": meta}) + "\n")
        for i, rec in enumerate(records, 1):
            t0 = time.time()
            try:
                raw = engine_fn(rec, args)
                err = None
            except Exception as e:  # capture, don't abort the run
                raw, err = "", f"{type(e).__name__}: {e}"
            row = {"id": rec["id"], "query": rec["user_query"], "raw_response": raw,
                   "error": err, "latency_s": round(time.time() - t0, 2)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            status = "ERR" if err else "ok"
            print(f"[{i}/{len(records)}] {rec['id']} {status} ({row['latency_s']}s)")

    print(f"\nrun written -> {out_path}")
    print(f"next: python3 report.py {out_path}")


if __name__ == "__main__":
    main()
