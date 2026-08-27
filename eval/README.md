# App Activation eval sets

This engine's charter (2026-08-27): App Activation only — every automation
it builds has to touch a real app via a connector action, and Track A
("Apps" panel) capabilities are app-only by construction. The two sets
below are the in-scope eval data. The general automation engine's eval
sets (real-world/multi-turn/entity/adversarial — pure Hiver automations
with no app action in any of them) moved to `legacy/eval/`; see that
directory's own README for what they covered.

```
python3 grader.py --self-test                  # canonicalize/diff self-consistency (connector-eval-set.jsonl)
python3 run_eval.py --engine echo               # pipeline dry-run against connector-eval-set.jsonl; report must say 100%
python3 report.py runs/<run>.jsonl --failures   # scoreboard + failure dump + needs_judge list

python3 apps_grader.py --self-test              # Track A's own small parallel harness
python3 run_eval.py --engine echo --eval-set apps-eval-set.jsonl
python3 apps_report.py runs/<run>.jsonl --failures
```

## Connector set (`connector-eval-set.jsonl`, added 2026-08-17)

6 records for the one validated connector recipe (`engine/schema.RECIPES`:
Salesforce auto-assign to the account's CSM). Requires `apps_ws` (`engine/
connected_apps.py`'s fixture) threaded through the harness — `cli.py
--apps-workspace` loads it, the same way `--workspace` loads `ws`.
con-001/002/003 test that the
recipe is matched (direct ask, drip-fed test-email slot, paraphrase without
the literal words "CSM"/"auto-assign"); con-004/005 test that a DIFFERENT
Salesforce action and a DIFFERENT app entirely both escalate to
`unsupported_requests` rather than being forced onto the one recipe; con-006
tests that "the account's CSM" alone (no literal "Salesforce") still routes
confidently — there is only one CSM-routing recipe, so the ambiguity a
broader vocabulary would have doesn't exist yet. This set is NOT runnable in
every environment: it needs a live LLM call (`OPENAI_API_KEY` + the
`openai` package), neither of which this repo's dev sandbox had when the
set was written — `engine/test_connector.py` covers the pure-code half
(validator + executor) that doesn't need either.

## Apps set (`apps-eval-set.jsonl`, added 2026-08-24)

12 records for Track A ("Apps" panel) capabilities ONLY —
`salesforce_account_contact_details` (view), `salesforce_create_contact`
(write), `clickup_create_task_from_hiver` (write) — plus `router.py`'s
boundary between Track A and Track B for those same capabilities. This is
deliberately narrower than the connector set above: it does not re-test
automation extraction correctness (that's the connector set's job), and it
does not cover connector recipes/native actions themselves beyond the
minimum needed to prove a phrase correctly stayed OUT of Track A (that's
connector-eval-set.jsonl's and `test_native_action.py`'s job).

Graded by a separate small harness (`apps_grader.py`/`apps_report.py`), NOT
an extension of `grader.py`/`report.py` — Track A's completed shape
(`feature_id`/`objects`/`fields_by_object`/`inboxes`, from `copilot.
to_final_feature_json()`, new in this pass) has no trigger or actions at
all, so forcing it through the automation-schema-shaped grader would mean
fighting that schema on every call.

- apps-001/002/003: `salesforce_account_contact_details` — the full 4-step
  wizard drip-fed one turn at a time, the same thing given in one dense
  turn, and a field REMOVED mid-flow (tests apps/extract.py's re-derive-the-
  whole-conversation rule for Track A specifically, which had never had
  eval coverage before this set).
- apps-004/005: `salesforce_create_contact` — the literal worked example
  from `router.py`'s own DISAMBIGUATION rule, and a dense single turn where
  the auth gate still blocks completion even though every other slot is
  already given.
- apps-006/007/008: `clickup_create_task_from_hiver` (capability 4's second
  app, 2026-08-24) — a subset of the 6 available fields, all 6 at once, and
  apps-008 opens with the EXACT text the Apps panel's own suggestion chip
  sends for this feature — the positive regression lock paired with the
  collision cases below.
- apps-009/010/011: `router_disambiguation` — THE bug found live on
  2026-08-24: `clickup_create_task_from_hiver` (Track A) and
  `NATIVE_ACTIONS['clickup_create_task']` (Track B) both describe "create a
  ClickUp task," and `router.py` had never listed Track B's own vocabulary
  at all, so it defaulted every such phrase to Track A once a Track A entry
  existed for the same app. apps-009 is the literal native-action suggestion
  chip text; apps-010 is the harder version (an explicit trigger AND full
  params in one sentence, so it must simultaneously escalate away from
  Track A and extract correctly into Track B); apps-011 guards the ORIGINAL
  write feature (Salesforce) against the same class of collision now that a
  second app has proven it can happen.
- apps-012: `router_view_vs_automation` — the FIRST router bug in this
  engagement (v2.8.1, "set up Salesforce account cards for my shared
  mailbox" misread as an automation), locked in since no eval set ever
  covered Track A routing at all before this file.

Graded two ways, chosen by what a record's `ideal_output` contains: records
with a `feature_id` are scripted all the way to `status: complete` and
diffed field-by-field (objects/fields/inboxes as set comparisons — order
never matters); records that are just `{"track": "..."}` (the router-
boundary cases, which can't reach completion in the scripted turns — a bare
"Create tasks automatically via automation" has no list/title yet on
either track) are graded purely on which track the output implies plus
`must_mention`/`must_not_mention` substrings, the same behavioral-assertion
mechanism `con-004`/`con-005` above already use for their own escalation
cases.

Like the connector set, every record needs a live LLM call to run for real
— `python3 apps_grader.py --self-test` and `python3 run_eval.py --engine
echo --eval-set apps-eval-set.jsonl` (100% by construction) prove the
harness's plumbing without one; a hand-driven full pipeline run (`router.
classify`/`apps.extract.extract`/`automation.extract.extract` stubbed the
same way `engine/test_track_a.py` already does) confirmed apps_report.py
correctly PASSES the fixed router behavior and correctly FAILS the exact
pre-fix bug (`clickup_create_task_from_hiver`'s name leaking into what
should have been a Track B turn) before this set was committed. Real run:

```
python3 run_eval.py --engine command \
    --cmd "python3 ../engine/cli.py --workspace --apps-workspace" \
    --eval-set apps-eval-set.jsonl --run-name apps-live
python3 apps_report.py runs/apps-live.jsonl --failures
```
