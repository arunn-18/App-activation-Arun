"""Report: grade a run of eval/apps-eval-set.jsonl and print the scoreboard.
report.py's peer for Track A ("Apps" panel) capabilities — see apps_grader.py's
docstring for why this is a separate small script rather than an extension of
report.py/grader.py.

  python3 apps_report.py runs/<run>.jsonl [--failures] [--out report.md]

Produce a run file the normal way first:
  python3 run_eval.py --engine echo --eval-set apps-eval-set.jsonl \\
      --run-name apps-echo-dryrun
  python3 run_eval.py --engine command \\
      --cmd "python3 ../engine/cli.py --workspace --apps-workspace" \\
      --eval-set apps-eval-set.jsonl --run-name apps-live

Every record needs BOTH --workspace (real shared-inbox names, for the
enable step both tracks now require) and --apps-workspace (connected_apps.json,
which starts every app disconnected — every record scripts its own "connect X"
turn rather than assuming a pre-connected fixture).
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import apps_grader
from report import parse_rule

HERE = Path(__file__).parent
EVAL_SET = HERE / "apps-eval-set.jsonl"


def grade_run(run_path, eval_set=EVAL_SET):
    eval_records = {r["id"]: r for r in map(json.loads, open(eval_set))}
    rows = [json.loads(l) for l in open(run_path)]
    meta = rows[0].get("_meta", {}) if rows and "_meta" in rows[0] else {}
    rows = [r for r in rows if "_meta" not in r]

    results = []
    for row in rows:
        rec = eval_records[row["id"]]
        transcript = row["raw_response"] or ""
        parsed, parse_status = parse_rule(transcript)
        if row.get("error"):
            parse_status = "engine_error"
        res = {"id": row["id"], "category": rec["category"], "difficulty": rec["difficulty"],
              "parse": parse_status, "engine_error": row.get("error")}
        if rec.get("turns"):
            res["n_copilot_turns"] = transcript.count("--- copilot[")

        is_full_completion = "feature_id" in rec["ideal_output"]
        if is_full_completion:
            d = apps_grader.diff_feature(rec["ideal_output"], parsed)
        else:
            # echo replays the ideal_output verbatim with no prose at all,
            # so a router-boundary record (no completed shape to echo) has
            # nothing meaningful to grade under --engine echo -- same
            # "behavior assertions skipped for echo" carve-out report.py's
            # entity-set grading already uses.
            if meta.get("engine") == "echo":
                d = {"match": True, "mismatches": ["skipped under --engine echo "
                                                    "(no transcript to check)"]}
            else:
                d = apps_grader.grade_router_boundary(rec, parsed, transcript)
        res["diff"] = d
        res["strict_pass"] = d["match"]
        results.append(res)
    return meta, results, eval_records


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def render(meta, results, eval_records, show_failures):
    lines = []
    w = lines.append
    n = len(results)
    strict = sum(1 for r in results if r.get("strict_pass"))
    w("# Apps (Track A) eval report")
    w(f"engine={meta.get('engine')} model={meta.get('model')} "
      f"run={meta.get('started')} records={n}")
    w("")
    w(f"## Headline: strict match {pct(strict, n)}")
    w("")
    parse_counts = Counter(r["parse"] for r in results)
    w(f"parse: {dict(parse_counts)}")
    mt = [r for r in results if "n_copilot_turns" in r]
    if mt:
        avg = sum(r["n_copilot_turns"] for r in mt) / len(mt)
        w(f"multi-turn: {len(mt)} records, avg {avg:.1f} copilot turns")
    w("")

    for dim, keyfn in (("difficulty", lambda r: [r["difficulty"]]),
                       ("category", lambda r: [r["category"]])):
        w(f"## By {dim}")
        buckets = defaultdict(list)
        for r in results:
            for k in keyfn(r):
                buckets[k].append(r)
        for k in sorted(buckets, key=lambda k: -len(buckets[k])):
            b = buckets[k]
            w(f"- {k}: {pct(sum(1 for r in b if r.get('strict_pass')), len(b))}")
        w("")

    if show_failures:
        w("## Failure dump")
        for r in results:
            if r.get("strict_pass"):
                continue
            rec = eval_records[r["id"]]
            w(f"### {r['id']}  [{r['category']} / {r['difficulty']}]")
            w(f"parse: {r['parse']}"
              + (f"  engine_error: {r['engine_error']}" if r.get("engine_error") else ""))
            w(f"query: {rec['user_query'][:250]}")
            for m in r["diff"]["mismatches"]:
                w(f"- {m}")
            w("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_file")
    p.add_argument("--failures", action="store_true", help="include per-record failure dump")
    p.add_argument("--out", help="also write the report to a markdown file")
    p.add_argument("--eval-set", default=str(EVAL_SET))
    args = p.parse_args()

    meta, results, eval_records = grade_run(args.run_file, args.eval_set)
    text = render(meta, results, eval_records, args.failures)
    print(text)
    if args.out:
        Path(args.out).write_text(text)
        print(f"[report written -> {args.out}]")


if __name__ == "__main__":
    main()
