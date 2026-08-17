# Real-world eval set

## Harness (added 2026-08-04)

```
python3 grader.py --self-test                 # 107 checks: every ideal_output vs itself + shape conversion + negative
python3 run_eval.py --engine echo --scope all # pipeline dry-run; report must say 100%
python3 run_eval.py --engine openai --scope core \
    --system-prompt <path> --model gpt-4o     # real run (needs OPENAI_API_KEY; v1 has one in its .env)
python3 report.py runs/<run>.jsonl --failures # scoreboard + failure dump + needs_judge list
```

- **`grader.py`** — `canonicalize()` maps both vocabularies (raw prod dump + engine output incl. v1's human-readable enums) into one form: vocab maps, group sorting, same-property OR-conditions merged (values are any-of), then `diff()` scores per slot (trigger / conditions / actions / ai_extract) with missing-vs-hallucinated detail. `TODO(v2-schema)` markers show where the frozen v2 enums must land.
- **`run_eval.py`** — capture-only runner (no grading, so grader fixes never re-cost API calls). Engines: `echo` (dry-run), `command` (any CLI), `openai` (system-prompt file). Run files in `runs/` carry engine/model/prompt-sha metadata.
- **`report.py`** — grades a run file: headline strict-match, slot table, slices by difficulty/category/flag, over-asking counter, failure dump, and a `needs_judge` list (Tier 3): mismatches where the only differences are op-swaps on identical property+values or near-identical values — never AND/OR restructuring.

**Baseline (2026-08-04)**: v1 prompt engine (gpt-4o, temp 0.2) on the 40 core-scope records — **27/40 strict (68%)**, +7 needs-judge (mostly `is` vs `contains` on full addresses → ceiling 34/40), 6 hard fails. Slots: actions 40/40, trigger 35/40, conditions 29/40. Report: `runs/baseline-v1-gpt4o-core.report.md`.

105 eval records mined from **real production automations** (prod `automation_ai` DB read-replica dump, 90-day window ending 2026-07-31, sync triggers only). Each record pairs a hand-written plain-English request (`user_query`) with the **actual automation an admin built** (`ideal_output`). This complements the hand-written v1 golden set (`../../automation-copilot/golden-dataset/`, 47 records): the golden set tests guardrail *behavior*; this set tests extraction *correctness* against the real-world distribution of rules.

## Provenance & pipeline (reproducible via `build/`)

1. **Source**: `~/Downloads/automations_sync_triggers_dump_90d/` — 6,412 automations / 16,885 steps from 1,088 tenants.
2. **Clean** (`build/mine_candidates.py`): active only, drop ~1,972 onboarding demo-seed clones, drop `old_automation_id` rows → 3,892 organic automations; exact-structure dedupe → 3,621.
3. **Sample**: stratified — quotas for the thin tail (AI steps, time conditions, connectors, custom fields/objects, multi-step conditions, non-inbound triggers, uncommon ops/actions), then head patterns spread across distinct structural signatures. Max 3 records per tenant. → 105 candidates (`build/candidates.jsonl`).
4. **Anonymize**: every real domain → `company-NN.example`; personal email local-parts → `personNN`; role addresses (support@, billing@…) keep their local part. Applied to condition values, note contents, mail fields.
5. **Author** (`build/annotations_*.json` + `build/build_eval_set.py`): a `user_query` written per record; opaque tenant IDs (`<tag:123>`, `<agent:456>`, `cf_789`, dropdown UUIDs) renamed to semantic names used consistently in the query; long value lists injected verbatim from the spec so query and target can't drift.

To regenerate: run `mine_candidates.py` (needs the dump + scratchpad paths adjusted), then `build_eval_set.py`.

## Record schema

| Field | Meaning |
|---|---|
| `id` | `rw-001` … `rw-105` (rw = real world) |
| `source_automation_id` | Prod automation id, for tracing back to the dump |
| `category` | Pattern label (27 values: `keyword_route`, `ai_classify`, `followup_nudge`, `connector`, …) |
| `difficulty` | easy 38 / medium 39 / hard 28 |
| `scope_flags` | Which non-core features the record uses (below). Empty = core scope. |
| `user_query` | The plain-English ask, as an admin would phrase it. Fully specified — target values, names, and lists are all in the query. |
| `ideal_output` | The real automation: `trigger`, `condition_groups`, `ai_extract`, `actions` — vocabulary is the **raw prod schema** (real trigger names, ops, action types) |
| `notes` | Oddities worth knowing when grading (see "Warts" below) |

### `ideal_output` semantics

- **Condition logic**: `condition_groups` is a list of groups; **groups are AND'd together; conditions within a group are OR'd**. (Verified against unambiguous samples, e.g. `[from is no-reply@x]` AND `[subject contains a, b, c]`.) A condition's `values` array is itself an any-of list.
- Records where the source had **2+ chained evaluation steps** are flattened into one AND'd group list and carry `source_eval_steps`.
- `ai_extract` holds the AI-step variable definitions (name, type, description, options); conditions reference them via `property: "ai_variable"`; actions reference them as `{{variable_name}}`.
- `send_mail` template bodies were not in the dump — those actions are correct as to *type*, with empty `fields`.
- `add_to_sm` / `remove_from_sm` / `send_notification` retain raw payload shapes with tenant-local inbox IDs (semantic name is in the query/notes).
- Dates/times are real: `time_slot` start/end are minutes-from-midnight with an explicit timezone.

### `scope_flags` — scoring is scope-decision-agnostic

The v2 copilot's supported surface isn't finalized (v1 excluded custom fields, time/date, connectors). Rather than baking that decision in, every record is flagged:

| Flag | n | Flag | n |
|---|---|---|---|
| *(none — core scope)* | 40 | `uses_time_condition` | 11 |
| `multi_condition` | 26 | `multi_step_conditions` | 10 |
| `uses_ai` | 18 | `uses_custom_field` | 7 |
| `non_inbound_trigger` | 18 | `uses_connector` | 6 |
| `uses_uncommon_action` | 18 | `uses_custom_object` | 2 |
| `uses_uncommon_operator` | 14 | | |

Filter at scoring time: for a v1-scoped engine, records with out-of-scope flags are *should-redirect* cases; for a fuller v2 scope, they're correctness cases.

## Warts preserved on purpose

Real data includes admin mistakes; the target is what the admin *built*, not what they should have built. Flagged in `notes`: rw-049 (thank-you closer that fires when actionable content IS present), rw-087 (self-contradictory AND on `from`), rw-056 ({{urgency_label}} referencing a variable named `urgency_level`), rw-069 (2-minute follow-up window, likely a test value), rw-053 (AI condition redundantly re-checking a keyword condition). These test faithful extraction; a copilot that *notices* the mistake and flags it should score bonus, not penalty.

## Known limits

- **Queries are reverse-authored** from the rules, so they're more fully-specified than real user asks. This set does not test the ask-first/clarification guardrails — that's the v1 golden set's job.
- One eval semantics assumption (AND-of-OR-groups) is inferred from data, not from the engine source — worth confirming with engineering before wiring a strict grader.
- The head of the distribution (subject/body contains → tag/assign/close) is deliberately down-weighted vs. reality (it's ~60% of prod but ~40% here); re-weight scores if you want a production-fidelity number.

## Multi-turn set (`multi-turn-eval-set.jsonl`, added 2026-08-09)

12 scripted conversations that give the clarification loop scored ground truth — the
piece the single-turn set can't test (see "Known limits" above). Each record carries
`turns` (fixed user messages, played in order by `cli.py`'s multi-turn mode) plus the
usual `ideal_output`; `run_eval.py --eval-set multi-turn-eval-set.jsonl` runs it and
`report.py --eval-set ...` grades the last JSON block and reports avg copilot turns.
Categories: vague openings (turns reuse real prod ideals: rw-006/010/020/045/046),
drip-fed values, linkage ambiguity (both resolutions of the rw-039 sim miss),
post-completion correction, batched numbered answers, unsupported-mix, scope
confirmation. Scripted answers assume the engine's deterministic question order
(trigger → scope → params); if that ordering changes, re-check the scripts.

## Entity set (`entity-eval-set.jsonl`, added 2026-08-09)

10 records for the workspace-aware path (`cli.py --workspace`, the only suite that
runs with the fixture loaded). Graded on two axes: the final rule must carry
canonical workspace names ("sarah" → target "Sarah Lee"), and the transcript must
show the right conduct via `must_mention` / `must_not_mention` substring assertions
(the two-Johns pick-one question, the create-first note for unknown tags, asking
instead of shopping the tag list when the user says "appropriately"). Behavior
assertions are skipped for `--engine echo`, which replays ideals without a
transcript. Covers: exact, casing-only, unique-fuzzy, ambiguous, unknown person
(with recovery turn), unknown tag, mixed known/unknown tags, inbox+person,
inbox+round-robin, and an invention bait.

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
broader vocabulary would have doesn't exist yet. Unlike the entity/multi-turn
sets above, this one is NOT runnable in every environment: it needs a live
LLM call (`OPENAI_API_KEY` + the `openai` package), neither of which this
repo's dev sandbox had when the set was written — `engine/test_connector.py`
covers the pure-code half (validator + executor) that doesn't need either.
