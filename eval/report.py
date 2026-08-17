"""Report: grade a run file against the eval set and print the scoreboard.

  python3 report.py runs/<run>.jsonl [--failures] [--out report.md]

Pipeline per record:
  Tier 1  parse the engine's raw response into rule JSON (fenced block, bare JSON,
          or last {...}); `null` = engine declined to build a rule.
  Tier 2  grader.canonicalize + grader.diff -> per-slot verdicts.
  Tier 3  records that failed strict match but look possibly-equivalent are written
          to <run>.needs_judge.jsonl for the LLM judge (not implemented here).
"""
import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import grader

HERE = Path(__file__).parent
EVAL_SET = HERE / "real-world-eval-set.jsonl"


# ------------------------------------------------------------------ parsing
def parse_rule(raw):
    """Extract rule JSON from an engine response. Returns (rule|None, status).
    status: ok | declined | parse_fail"""
    if raw is None or not raw.strip():
        return None, "parse_fail"
    fences = re.findall(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    candidates = fences if fences else [raw]
    for cand in reversed(candidates):  # last block wins (v1 replies prose first)
        cand = cand.strip()
        if cand.lower() in ("null", "none"):
            return None, "declined"
        try:
            obj = json.loads(cand)
            if obj is None:
                return None, "declined"
            if isinstance(obj, dict):
                return obj, "ok"
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)  # last resort: outermost braces
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj, "ok"
        except json.JSONDecodeError:
            pass
    return None, "parse_fail"


def looks_like_clarification(raw):
    if not raw:
        return False
    tail = raw.strip()[-300:]
    return "?" in tail


# ------------------------------------------------------------------ grading
def grade_run(run_path, eval_set=EVAL_SET):
    eval_records = {r["id"]: r for r in map(json.loads, open(eval_set))}
    rows = [json.loads(l) for l in open(run_path)]
    meta = rows[0].get("_meta", {}) if rows and "_meta" in rows[0] else {}
    rows = [r for r in rows if "_meta" not in r]

    results = []
    for row in rows:
        rec = eval_records[row["id"]]
        rule, status = parse_rule(row["raw_response"])
        res = {"id": row["id"], "difficulty": rec["difficulty"],
               "category": rec["category"], "flags": rec["scope_flags"],
               "parse": status, "engine_error": row.get("error"),
               "asked_clarification": status != "ok" and looks_like_clarification(row["raw_response"])}
        if rec.get("turns"):  # multi-turn record: transcript carries turn markers
            res["n_copilot_turns"] = (row["raw_response"] or "").count("--- copilot[")
        if row.get("error"):
            res["parse"] = "engine_error"
        if res["parse"] == "ok":
            exp_c = grader.canonicalize(rec["ideal_output"])
            got_c = grader.canonicalize(rule)
            d = grader.diff(exp_c, got_c)
            res["diff"] = d
            res["strict_pass"] = d["strict_pass"]
            if not d["strict_pass"]:
                res["needs_judge"] = is_near_miss(d, exp_c, got_c)
        else:
            res["strict_pass"] = False
        # behavior assertions (entity slice): the transcript itself must show the
        # right conduct — the pick-one question, the create-first note, an ask
        # instead of a guess. Echo replays the ideal rule with no transcript, so
        # these only apply to real engine runs.
        if meta.get("engine") != "echo":
            transcript = row["raw_response"] or ""
            res["behavior_missing"] = [s for s in rec.get("must_mention") or []
                                       if s not in transcript]
            res["behavior_forbidden"] = [s for s in rec.get("must_not_mention") or []
                                         if s in transcript]
            if res["behavior_missing"] or res["behavior_forbidden"]:
                res["strict_pass"] = False
        results.append(res)
    return meta, results, eval_records


def _flat_conds(canon):
    return sorted(c for g in canon["groups"] for c in g)


def is_near_miss(d, exp_c, got_c):
    """True when every difference looks like a semantically-equivalent encoding
    the deterministic grader can't rule on — an op swap on the same property+values
    ('is' vs 'contains' on a full address), or near-identical values (punctuation).
    Group-logic differences (AND vs OR restructuring) are NOT near-misses."""
    if not d.get("trigger", {}).get("match"):
        return False
    if d["actions"]["missing"] or d["actions"]["hallucinated"]:
        return False
    ai = d.get("ai_extract")
    if ai and (ai["missing"] or ai["hallucinated"]):
        return False
    exp, got = _flat_conds(exp_c), _flat_conds(got_c)
    if len(exp) != len(got):
        return False
    # group shape must match (same number of groups, same sizes) so we never
    # judge away an AND/OR restructuring
    if sorted(len(g) for g in exp_c["groups"]) != sorted(len(g) for g in got_c["groups"]):
        return False
    unmatched_got = [c for c in got if c not in exp]
    for miss in (c for c in exp if c not in got):
        prop, op, values, extras = miss
        mate = None
        for cand in unmatched_got:
            if cand[0] != prop or cand[3] != extras:
                continue
            same_vals = cand[2] == values
            fuzzy = difflib.SequenceMatcher(
                None, " | ".join(values), " | ".join(cand[2])).ratio() >= 0.85
            if same_vals or fuzzy:
                mate = cand
                break
        if mate is None:
            return False
        unmatched_got.remove(mate)
    return True


# ---------------------------------------------------------------- reporting
def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def slot_accuracy(results, slot):
    graded = [r for r in results if "diff" in r]
    if not graded:
        return "n/a"
    if slot == "trigger":
        good = sum(1 for r in graded if r["diff"]["trigger"]["match"])
        return pct(good, len(graded))
    perfect = sum(1 for r in graded
                  if not r["diff"][slot]["missing"] and not r["diff"][slot]["hallucinated"])
    return pct(perfect, len(graded))


def render(meta, results, eval_records, show_failures):
    lines = []
    w = lines.append
    n = len(results)
    strict = sum(1 for r in results if r.get("strict_pass"))
    w(f"# Eval report")
    w(f"engine={meta.get('engine')} model={meta.get('model')} scope={meta.get('scope')} "
      f"prompt_sha={meta.get('prompt_sha') or '-'} run={meta.get('started')}")
    w("")
    w(f"## Headline: strict full-rule match {pct(strict, n)}")
    w("")
    parse_counts = Counter(r["parse"] for r in results)
    w(f"parse: {dict(parse_counts)}   "
      f"clarification-asks (over-asking, queries are fully specified): "
      f"{sum(1 for r in results if r['asked_clarification'])}")
    mt = [r for r in results if "n_copilot_turns" in r]
    if mt:
        avg = sum(r["n_copilot_turns"] for r in mt) / len(mt)
        w(f"multi-turn: {len(mt)} records, avg {avg:.1f} copilot turns, "
          f"completed (rule produced): {sum(1 for r in mt if r['parse'] == 'ok')}/{len(mt)}")
    w("")
    w("## Slot accuracy (among parsed rules)")
    for slot in ("trigger", "conditions", "actions"):
        w(f"- {slot}: {slot_accuracy(results, slot)}")
    ai_records = [r for r in results if "diff" in r and r["diff"]["ai_extract"] is not None]
    if ai_records:
        good = sum(1 for r in ai_records
                   if not r["diff"]["ai_extract"]["missing"]
                   and not r["diff"]["ai_extract"]["hallucinated"])
        w(f"- ai_extract: {pct(good, len(ai_records))}")
    w("")

    for dim, keyfn in (("difficulty", lambda r: [r["difficulty"]]),
                       ("category", lambda r: [r["category"]]),
                       ("scope flag", lambda r: r["flags"] or ["(core)"])):
        w(f"## By {dim}")
        buckets = defaultdict(list)
        for r in results:
            for k in keyfn(r):
                buckets[k].append(r)
        for k in sorted(buckets, key=lambda k: -len(buckets[k])):
            b = buckets[k]
            w(f"- {k}: {pct(sum(1 for r in b if r.get('strict_pass')), len(b))}")
        w("")

    judge = [r for r in results if r.get("needs_judge")]
    w(f"## Tier-3 (needs judge): {len(judge)} records")
    w("")

    if show_failures:
        w("## Failure dump")
        for r in results:
            if r.get("strict_pass"):
                continue
            rec = eval_records[r["id"]]
            w(f"### {r['id']}  [{r['category']} / {r['difficulty']}"
              f"{' / ' + ','.join(r['flags']) if r['flags'] else ''}]"
              f"{'  → needs_judge' if r.get('needs_judge') else ''}")
            w(f"parse: {r['parse']}"
              + (f"  engine_error: {r['engine_error']}" if r.get("engine_error") else ""))
            w(f"query: {rec['user_query'][:250]}")
            for s in r.get("behavior_missing") or []:
                w(f"- behavior: transcript never says {s!r}")
            for s in r.get("behavior_forbidden") or []:
                w(f"- behavior: transcript must not say {s!r}, but does")
            if "diff" in r:
                d = r["diff"]
                if not d["trigger"]["match"]:
                    w(f"- trigger: expected {d['trigger']['expected']}, got {d['trigger']['got']}")
                for slot in ("conditions", "actions"):
                    for kind in ("missing", "hallucinated"):
                        for item in d[slot][kind]:
                            w(f"- {slot} {kind}: {item[:200]}")
                if d["ai_extract"]:
                    for kind in ("missing", "hallucinated"):
                        for item in d["ai_extract"][kind]:
                            w(f"- ai_extract {kind}: {item[:200]}")
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

    judge = [r for r in results if r.get("needs_judge")]
    if judge:
        jp = Path(args.run_file).with_suffix(".needs_judge.jsonl")
        with open(jp, "w") as f:
            for r in judge:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n[tier-3 candidates written -> {jp}]", file=sys.stderr)
    if args.out:
        Path(args.out).write_text(text)
        print(f"[report written -> {args.out}]", file=sys.stderr)


if __name__ == "__main__":
    main()
