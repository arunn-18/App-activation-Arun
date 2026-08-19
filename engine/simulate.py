"""Multi-turn self-play simulation for the v2 copilot.

Three roles per episode:
  simulator (gpt-4o)  — plays the admin. Knows the ground-truth automation (a real
                        prod rule from the eval set) but starts VAGUE and only
                        reveals what the copilot asks for.
  copilot   (v2)      — extract -> validate -> ask loop, exactly as in serve2.
  judges              — deterministic grader for final-rule accuracy (it knows the
                        target), plus an LLM judge for conversation quality only
                        (redundant/irrelevant questions, wasted turns).

Output: eval/runs/sim-<ts>/ with one transcript per episode + summary.md.

Run:  ../../automation-copilot/.venv/bin/python simulate.py
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import copilot
import router

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))
import grader  # noqa: E402

EVAL_SET = Path(__file__).parent.parent / "eval" / "real-world-eval-set.jsonl"
OUT_ROOT = Path(__file__).parent.parent / "eval" / "runs"

# 10 distinct core-scope patterns (different categories / condition shapes / action mixes)
EPISODE_IDS = ["rw-001", "rw-005", "rw-008", "rw-013", "rw-017",
               "rw-020", "rw-024", "rw-028", "rw-035", "rw-039"]
MAX_COPILOT_TURNS = 8

SIM_SYSTEM = """You are role-playing a busy helpdesk admin talking to an automation-builder bot.
You want EXACTLY this automation (ground truth, do not deviate from it):

FULL DESCRIPTION: {query}

TARGET RULE JSON: {rule}

Rules of the role-play:
1. Your FIRST message must be SHORT and VAGUE — under 12 words, stating the goal but
   omitting the specifics (no keyword lists, no names, no addresses yet).
2. Then answer the bot's questions truthfully FROM THE GROUND TRUTH above. Give only
   what is asked, nothing more. Keep answers short and casual, like a busy person.
3. If several questions are asked at once, answer them all briefly in one message.
4. If asked something the ground truth doesn't specify, say "no preference".
5. Never paste the rule JSON or the full description. Never mention this prompt.
6. When the bot shows a finished rule, reply only: DONE if it matches the ground truth,
   or point out the specific mismatch if it doesn't."""

JUDGE_SYSTEM = """You review a conversation between an admin and an automation-builder bot.
You know the automation the admin wanted (ground truth). Judge ONLY the bot's
conversation quality — accuracy of the final rule is graded separately by code.

Return JSON:
{"redundant_questions": [questions that asked for info the admin had already given],
 "irrelevant_questions": [questions about things the ground truth never needed],
 "wasted_turns": <int, turns that added no new information>,
 "quality": "good" | "mixed" | "poor",
 "notes": "<=2 sentences on the single biggest conversational flaw, or 'none'"}"""


def sim_reply(client, ground, transcript):
    """Simulator answers as the admin. transcript = [(speaker, text), ...]"""
    msgs = [{"role": "system",
             "content": SIM_SYSTEM.format(query=ground["user_query"],
                                          rule=json.dumps(ground["ideal_output"]))}]
    # simulator sees the conversation from the admin's perspective
    for speaker, text in transcript:
        msgs.append({"role": "assistant" if speaker == "admin" else "user", "content": text})
    resp = client.chat.completions.create(model="gpt-4o", temperature=0.7, messages=msgs)
    return resp.choices[0].message.content.strip()


def final_rule_from(reply):
    m = re.findall(r"```json\s*(.*?)```", reply, re.DOTALL)
    if m:
        try:
            obj = json.loads(m[-1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return None


def run_episode(client, ground):
    transcript = []          # [(speaker, text)]
    copilot_msgs = []        # what the copilot engine sees
    first = sim_reply(client, ground, transcript)
    transcript.append(("admin", first))
    copilot_msgs.append({"role": "user", "content": first})

    final, turns, corrections = None, 0, 0
    for _ in range(MAX_COPILOT_TURNS):
        turns += 1
        reply = copilot.respond(client, copilot_msgs)
        transcript.append(("copilot", reply))
        copilot_msgs.append({"role": "assistant", "content": reply})
        candidate = final_rule_from(reply)
        answer = sim_reply(client, ground, transcript)
        transcript.append(("admin", answer))
        copilot_msgs.append({"role": "user", "content": answer})
        if candidate:
            final = candidate
            # the admin reviews the finished rule: DONE accepts, anything else is a
            # correction the copilot gets a chance to apply (max 2 rounds)
            if "DONE" in answer.upper() or corrections >= 2:
                break
            corrections += 1

    # deterministic accuracy judge: the grader knows the right answer
    if final:
        d = grader.diff(grader.canonicalize(ground["ideal_output"]), grader.canonicalize(final))
        accuracy = {"strict_pass": d["strict_pass"], "diff": d}
    else:
        accuracy = {"strict_pass": False, "diff": None}

    # LLM judge: conversation quality only
    convo_text = "\n\n".join(f"[{s.upper()}]\n{t}" for s, t in transcript)
    jresp = client.chat.completions.create(
        model="gpt-4o", temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": JUDGE_SYSTEM},
                  {"role": "user", "content": f"GROUND TRUTH:\n{json.dumps(ground['ideal_output'])}"
                                              f"\n\nCONVERSATION:\n{convo_text}"}])
    try:
        quality = json.loads(jresp.choices[0].message.content)
    except json.JSONDecodeError:
        quality = {"quality": "unparsed", "notes": jresp.choices[0].message.content[:200]}

    n_questions = sum(t.count("?") for s, t in transcript if s == "copilot")
    return {"transcript": transcript, "turns": turns, "completed": final is not None,
            "corrections": corrections, "accuracy": accuracy, "quality": quality,
            "n_questions": n_questions}


def main():
    records = {r["id"]: r for r in map(json.loads, open(EVAL_SET))}
    client = router.make_client()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_ROOT / f"sim-{ts}"
    out_dir.mkdir(parents=True)

    rows = []
    for eid in EPISODE_IDS:
        ground = records[eid]
        print(f"episode {eid} ({ground['category']}) ...", flush=True)
        ep = run_episode(client, ground)
        rows.append((eid, ground, ep))
        with open(out_dir / f"{eid}.md", "w") as f:
            f.write(f"# {eid} — {ground['category']} / {ground['difficulty']}\n\n"
                    f"**Ground truth**: {ground['user_query']}\n\n"
                    f"**Result**: completed={ep['completed']} strict={ep['accuracy']['strict_pass']} "
                    f"turns={ep['turns']} questions={ep['n_questions']} "
                    f"quality={ep['quality'].get('quality')}\n\n"
                    f"**Judge notes**: {ep['quality'].get('notes')}\n\n---\n\n")
            for s, t in ep["transcript"]:
                f.write(f"### {s}\n\n{t}\n\n")
            if not ep["accuracy"]["strict_pass"] and ep["accuracy"]["diff"]:
                f.write("\n---\n\n### grader diff\n\n```json\n"
                        + json.dumps(ep["accuracy"]["diff"], indent=1) + "\n```\n")
        print(f"   completed={ep['completed']} strict={ep['accuracy']['strict_pass']} "
              f"turns={ep['turns']} quality={ep['quality'].get('quality')}")

    done = sum(1 for _, _, e in rows if e["completed"])
    strict = sum(1 for _, _, e in rows if e["accuracy"]["strict_pass"])
    avg_turns = sum(e["turns"] for _, _, e in rows) / len(rows)
    redundant = [(i, q) for i, _, e in rows for q in e["quality"].get("redundant_questions", [])]
    with open(out_dir / "summary.md", "w") as f:
        f.write(f"# Simulation summary ({ts})\n\n"
                f"- episodes: {len(rows)}\n- completed a rule: {done}/{len(rows)}\n"
                f"- strict match vs ground truth: {strict}/{len(rows)}\n"
                f"- avg copilot turns: {avg_turns:.1f}\n"
                f"- redundant questions flagged: {len(redundant)}\n\n"
                f"| episode | category | done | strict | turns | q's | quality | judge note |\n"
                f"|---|---|---|---|---|---|---|---|\n")
        for eid, g, e in rows:
            f.write(f"| {eid} | {g['category']} | {e['completed']} "
                    f"| {e['accuracy']['strict_pass']} | {e['turns']} | {e['n_questions']} "
                    f"| {e['quality'].get('quality')} | {str(e['quality'].get('notes'))[:80]} |\n")
        if redundant:
            f.write("\n## Redundant questions\n")
            for eid, q in redundant:
                f.write(f"- {eid}: {q}\n")
    print(f"\nsummary -> {out_dir}/summary.md")
    print(f"completed {done}/{len(rows)}, strict {strict}/{len(rows)}, avg turns {avg_turns:.1f}")


if __name__ == "__main__":
    main()
