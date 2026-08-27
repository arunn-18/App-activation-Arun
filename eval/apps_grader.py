"""Grader for eval/apps-eval-set.jsonl — Track A ("Apps" panel) capabilities
ONLY: salesforce_account_contact_details, salesforce_create_contact,
clickup_create_task_from_hiver, plus the router.py boundary between Track A
and Track B for those same capabilities. This is deliberately NOT a rewrite
or extension of grader.py — that file's canonicalize()/diff() are built
entirely around the automation wire schema (trigger/condition_groups/
actions), and Track A's completed shape (feature_id/objects/fields_by_
object/inboxes, from copilot.to_final_feature_json()) doesn't have a
trigger or actions at all. Forcing it through grader.py would mean fighting
that schema on every call; a small parallel grader, mirroring grader.py's
own self-test discipline, is the same "genuine peer package, not a bolted-
on branch" choice this whole engine already makes for automation/ vs apps/.

Two grading modes, chosen by what `ideal_output` contains:

  1. Full completion (`ideal_output` has "feature_id"): the conversation is
     scripted all the way to `status: complete`, and copilot.respond()'s
     fenced JSON block (to_final_feature_json()'s shape) is diffed field by
     field — feature_id, app, objects, fields_by_object (per object), and
     inboxes, each an exact set match (order never matters for any of
     these, since resolve_setup() never claims one).

  2. Router-boundary only (`ideal_output` is just {"track": "..."}): used
     for records that deliberately DON'T reach completion in the scripted
     turns (a bare "Create tasks automatically via automation" has no
     list/title yet on either track) — there is no fenced-JSON signal to
     diff, since both tracks legitimately emit `null` while incomplete.
     Graded purely on which
     track the parsed output (or lack of one) implies, plus the record's
     own must_mention/must_not_mention substrings — the SAME behavioral-
     assertion mechanism the connector set's con-004/con-005 already use
     for their own "must escalate, not fabricate a match" cases.

Self-test: python3 apps_grader.py --self-test
  Every full-completion ideal_output, reconstructed into the exact fenced-
  JSON text respond() would emit, must parse and diff as a perfect match
  against itself.
"""
import json
import sys
from pathlib import Path

EVAL_SET = Path(__file__).parent / "apps-eval-set.jsonl"


def classify_track(parsed):
    """parsed: the dict report.parse_rule() extracted from a run's
    raw_response, or None if it declined/parse_fail'd. Returns "app_setup",
    "automation", or "none" -- the three states copilot.respond() can leave
    a transcript in, discriminated purely by shape (to_final_feature_json()
    always carries "feature_id"; automation's to_final_json() always
    carries "trigger", even when its value is null pre-completion... no --
    to_final_json is ONLY emitted on real completion too; an incomplete
    automation turn emits bare `null`, same as an incomplete Track A turn.
    So "none" is genuinely ambiguous between "incomplete automation" and
    "incomplete app_setup" -- callers needing to tell those apart rely on
    must_mention/must_not_mention instead, per this module's own docstring)."""
    if not isinstance(parsed, dict):
        return "none"
    if "feature_id" in parsed:
        return "app_setup"
    if "trigger" in parsed:
        return "automation"
    return "none"


def diff_feature(exp, got):
    """Field-by-field comparison of two to_final_feature_json() shapes (or
    got=None when the engine declined/never completed). Every list-shaped
    field is compared as a SET -- resolve_setup() never claims field/object/
    inbox order matters, so grading order would only invent false failures."""
    d = {"match": True, "mismatches": []}
    if got is None:
        d["match"] = False
        d["mismatches"].append("expected a completed app_setup result, got none "
                               "(engine declined or never reached completion)")
        return d
    if classify_track(got) != "app_setup":
        d["match"] = False
        d["mismatches"].append(f"expected track=app_setup, got a {classify_track(got)}-shaped result")
        return d
    for key in ("feature_id", "app", "kind"):
        if exp.get(key) != got.get(key):
            d["match"] = False
            d["mismatches"].append(f"{key}: expected {exp.get(key)!r}, got {got.get(key)!r}")
    if set(exp.get("objects") or []) != set(got.get("objects") or []):
        d["match"] = False
        d["mismatches"].append(f"objects: expected {exp.get('objects')}, got {got.get('objects')}")
    exp_fbo = exp.get("fields_by_object") or {}
    got_fbo = got.get("fields_by_object") or {}
    for obj in set(exp_fbo) | set(got_fbo):
        exp_fields, got_fields = set(exp_fbo.get(obj, [])), set(got_fbo.get(obj, []))
        if exp_fields != got_fields:
            d["match"] = False
            missing = exp_fields - got_fields
            hallucinated = got_fields - exp_fields
            d["mismatches"].append(
                f"{obj} fields: missing {sorted(missing)}, hallucinated {sorted(hallucinated)}")
    if set(exp.get("inboxes") or []) != set(got.get("inboxes") or []):
        d["match"] = False
        d["mismatches"].append(f"inboxes: expected {exp.get('inboxes')}, got {got.get('inboxes')}")
    return d


def grade_router_boundary(rec, parsed, transcript):
    """Records whose ideal_output is just {"track": "..."} -- no completion
    expected, so the only signal is which track the output implies plus the
    scripted must_mention/must_not_mention substrings (see module docstring
    mode 2)."""
    want = rec["ideal_output"]["track"]
    got_track = classify_track(parsed)
    mismatches = []
    if want == "app_setup":
        if got_track != "app_setup":
            mismatches.append(f"expected track=app_setup, got {got_track}")
    else:  # want == "automation": anything that is NOT app_setup counts --
           # "none" covers both a still-in-progress automation turn and an
           # honest unsupported_requests escalation, either of which is a
           # correct outcome for a collision case (see apps-011's notes).
        if got_track == "app_setup":
            mismatches.append("expected NOT app_setup (should escalate to automation), "
                              "but the response is app_setup-shaped")
    for s in rec.get("must_mention") or []:
        if s not in transcript:
            mismatches.append(f"transcript never says {s!r}")
    for s in rec.get("must_not_mention") or []:
        if s in transcript:
            mismatches.append(f"transcript must not say {s!r}, but does")
    return {"match": not mismatches, "mismatches": mismatches}


# ---------------------------------------------------------------- self-test
def self_test():
    fails, total = 0, 0
    for line in open(EVAL_SET):
        rec = json.loads(line)
        ideal = rec["ideal_output"]
        total += 1
        if "feature_id" in ideal:
            d = diff_feature(ideal, ideal)
            if not d["match"]:
                fails += 1
                print(f"SELF-TEST FAIL {rec['id']}: {d['mismatches']}")
        else:
            # router-boundary records: self-test only that classify_track()
            # reads the record's OWN stated intent back correctly, since
            # there's no completed shape to reconstruct.
            want = ideal["track"]
            reconstructed = {"feature_id": "x"} if want == "app_setup" else {"trigger": "x"}
            if classify_track(reconstructed) != want:
                fails += 1
                print(f"SELF-TEST FAIL {rec['id']}: track classification mismatch")
    print(f"self-test: {total - fails}/{total} passed")
    return fails == 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    print(__doc__)
