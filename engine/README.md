# v2 engine — structured spec + code validator

Plain English → legal Hiver automation, via a hard split of responsibilities:
the **model only extracts**, the **code decides**. Built 2026-08-07.

## Flow (per turn)

1. `extract.py` — gpt-4o with strict structured output maps the whole conversation onto a
   **partial rule spec**: legal vocabulary only, unknown slots left null/empty, unsupported
   asks listed separately. It never plans questions and never judges completeness.
2. `validator.py` — pure code. Checks enum validity, per-property operators, trigger×condition
   compatibility, required action params, scope (bare plurals ≠ "all"), and **provenance**:
   every free-text value (tags, people, keywords, addresses, inboxes) must literally appear in
   the user's own messages — hallucinated values are scrubbed and re-asked, which is what kills
   the "invented VIP tag" failure class v1 could not fix at the prompt level (3 attempts).
3. `copilot.py` — renders the reply: closest legal structure with ⟨required — not provided yet⟩
   markers, unsupported asks called out, up to 3 planned questions per turn (trigger → scope →
   action params), repeating until complete; then the final WHEN/IF/THEN + machine JSON.

## Files

| file | role |
|---|---|
| `schema.py` | The legal vocabulary (7 triggers, 16 condition properties + per-property ops incl. `ai_variable`, 7 AI variable types, 11 actions + required params), grounded in the 90d prod dump. `UNSUPPORTED` names what we recognize but don't build. `RECIPES` + `FEATURES` (v2.8) hold the connector/Track-A vocabulary — see below. |
| `validator.py` | validate(spec, conversation, ws=None, apps_ws=None) → status/errors/missing/hallucinated/resolutions/entity_notes/questions. `scrub()` removes unproven values; `apply_resolutions()` rewrites resolved values to canonical workspace names. `apps_ws` (v2.8) re-checks a connector action's recipe prerequisites. |
| `workspace.py` / `workspace.json` | Demo workspace fixture (tags, agents incl. two Johns, shared inboxes) + deterministic resolvers (exact / resolved / ambiguous / none), the LLM tool schemas, and `verified_source()` — the code-side re-check of every model lookup. |
| `connected_apps.py` / `connected_apps.json` (v2.8) | Which third-party apps are connected + their prerequisite flags (e.g. Salesforce Account Team enabled). Same load()/check split as workspace.py, kept separate because it's state about the APPS, not Hiver entities. |
| `salesforce_mock.py` / `salesforce_fixture.json` (v2.8) | Mock Salesforce service for the one connector recipe: contact→account lookup, account-team-CSM lookup. Raw REST/SOQL-shaped response envelopes, so a test-run's captured responses look like what production would return. |
| `executor.py` (v2.8) | Fires a `RECIPES` chain for real (against the mock service today): template-fills `{{variable}}` refs between steps, captures raw responses, stops cleanly (`status: no_match`) instead of throwing when a step can't produce what's needed. |
| `features.py` (v2.8) | Track A: enabling an existing App feature (`schema.FEATURES`) — not an automation, no trigger/conditions/chain, Apps-panel-only. |
| `test_validator.py` | Schema coverage (every core-scope eval record must validate complete) + unit cases. Run on every schema/validator change. |
| `test_connector.py` (v2.8) | Pure-code connector tests: happy path, CSM-vs-AE role filter, no-CSM clean failure, provenance rejection, the downstream half of no-match escalation, plus Track A prerequisite gating. No LLM call, no API key needed. |
| `extract.py` | Extraction prompt + strict JSON schema + env/client helpers. `RECIPES` vocab + routing rule (v2.8) added. |
| `copilot.py` | Turn loop + rendering + grader-compatible final JSON. `connector_test_run()` (v2.8) fires a completed connector rule's recipe before it's shown as done. |
| `cli.py` | stdin query → stdout reply (used by `../eval/run_eval.py --engine command`). |
| `serve2.py` | Automations-panel chat UI at http://127.0.0.1:8001 (`../../automation-copilot/.venv/bin/python serve2.py`). Now also loads `connected_apps.json` so connector rules test-run from this panel too. |
| `serve_api.py` | Structured JSON API at http://127.0.0.1:8010 (`respond_structured()`: status, spec, questions, resolutions, final rule, `test_run`). The Next.js playground at `~/sandbox/automation-copilot-ui` builds on it. |
| `serve_apps.py` (v2.8) | Apps-panel entry point at http://127.0.0.1:8011, scoped to one connected app — Track A features + Track B recipes for that app. Imports the SAME schema/extract/validator/copilot/executor as the Automations panel; no forked engine. |

## Eval results (core-40, ../eval/)

| run | strict | trigger | conditions | actions | over-asks |
|---|---|---|---|---|---|
| v1 prompt engine (baseline) | 27/40 | 88% | 72% | 100%* | 0 |
| v1.1 (ask-first fixes) | 28/40 | 95% | 72% | 100% | 0 |
| v2 first run | 16/40 | 70% | 85% | 100% | **13** (asked trigger) |
| v2.1 (+trigger default = inbound, disclosed) | 33/40 | 98% | 85% | 100% | 0 |
| v2.2 (+OR-grouping rule) | 31/40 | 98% | 80% | 100% | 0 — example primed `is`, broke 5 |
| v2.3 (+op-choice rule) | 36/40 (90%) | 98% | 92% | 100% | 0 |
| v2.4.3 (+ai_extract, verbatim-quote rule) | 36/40 (90%) | 98% | 92% | 100% | 0 |
| **v2.5.4 (+from-contains default, anti-placeholder)** | **37/40 (92%)** | 98% | 95% | 100% | 0 |

Remaining 3 (v2.5.4): rw-004 (ambiguous any-direction trigger), rw-015/034 = needs-judge
op equivalences. The from-contains rule — found by the multi-turn eval, not by core —
fixed rw-010/017/019. Judge-adjusted ceiling ≈ 39/40.

Lessons encoded in the extraction rules: trigger defaults to inbound when unstated (82% of
prod) with the assumption disclosed; user "or"/"and" maps to within-group / across-groups;
`contains` is the default operator (to/cc always), `is` only on "exactly".

## Multi-turn simulation (`simulate.py`)

Self-play harness for the clarification loop: a simulator LLM plays the admin — it knows a
real prod rule (ground truth from the eval set) but opens vague (<12 words) and only answers
what's asked; the copilot runs its loop; when a rule is produced the "admin" reviews it and
can send up to 2 corrections. Accuracy is judged by the deterministic grader (it knows the
target); an LLM judge scores conversation quality only (redundant/irrelevant questions).
Transcripts + summary land in `../eval/runs/sim-<ts>/`.

First runs (2026-08-07, 10 episodes): initial 10/10 completed but 5/10 strict — surfaced a
real bug (copilot took the admin's echoed mechanism-language "specific senders" as a literal
match value; fixed with a META_VALUES guard in the validator + extraction rule 7) and a
harness gap (no correction round). After fixes: **10/10 completed, 9/10 strict, avg 2.9
turns, zero redundant questions**. Remaining miss: AND vs OR linkage when conditions arrive
in separate turns — a genuine ambiguity the copilot should ask about (see Next).

## AI extraction (v2.4, 2026-08-09) — engine capability, OUT of pilot scope

> **Scope decision (2026-08-09):** AI-based automation building is a separate team's
> project; the two merge in production. This project's pilot pitch is the non-AI
> surface only (92.2% of the non-AI pool). Everything below stays in the engine as a
> built-and-measured gated extension for that merge; the uses_ai eval slice remains a
> regression suite, not a pilot claim. rule-menu.md's proposed exclusion: resolved.

`ai_extract` moved from UNSUPPORTED to the schema: variables (7 types; single_select
carries options), `ai_variable` conditions (is / is_any_of / exists / does_not_exist),
`{{variable}}` references in note bodies. Validator additions: conditions must reference
a declared variable, booleans gate only on true/false, select values must be options,
single_select without options is asked, option labels carry provenance, dangling
`{{refs}}` are errors (the coverage suite proves this catches a real admin's typo, rw-056).

Grading decision (see grader.py): AI variable **names are arbitrary identifiers** no
engine can guess ("is_hts_coo_dimensions_related"), and note bodies with `{{refs}}` are
model-authored prose — so variables compare as a multiset of (type, options), ai
conditions on the referenced variable's type, templated notes on shape (ref count +
pinned), same spirit as send_mail bodies. Names/descriptions stay ungraded.

Runs on the 18-record `uses_ai` slice (16 in supported scope — 2 need custom fields):

| run | strict | what changed |
|---|---|---|
| v2.4 (vocabulary only) | 8/18 | first wiring; gates lumped into one group, labels snake_cased |
| v2.4.1 (+gating rules) | 10/18 | every stated gate becomes a condition, own group per AND'd gate |
| v2.4.2 (+one-var-per-fact, exists-gates, keep-status) | 12/18 | unreferenced facts get variables; "if present" creates exists gates |
| **v2.4.3 (+verbatim-quote rule)** | **12/18 (12/16 supported = 75%)** | fixed the core regression (rw-019 split a quoted value on '/') |

Remaining 6, categorized: rw-051/052 custom fields (out of scope, correctly named, not
faked), rw-050 needs `time_slot`/timezone on date conditions (real vocabulary gap),
rw-043 encoding ambiguity (admin: boolean+text; engine: single_select — judge-class),
rw-047/048 admins declared helper variables (5 vs the 2 the query implies) that no
query-faithful extractor can reproduce; their gate wiring matches.

## Entity validation + tool calling (v2.5, 2026-08-09)

The copilot now knows what exists. `workspace.json` is a demo fixture (production would
be Hiver's APIs with the admin's session); extraction gains a bounded tool-calling loop
(`list_tags`, `find_user`, `list_inboxes`) so the model can canonicalize what the user
names ("sarah" → "Sarah Lee"). The v2 guarantee holds through a new rule:

> **The model may look things up, but code re-verifies every lookup.**

`validator.verified_source()` re-runs the same deterministic resolution over the user's
own words; a canonical value the model filled is accepted only if some phrase the user
actually typed resolves uniquely to it. Outcomes, per the entity-resolution policy:

- **exact** match → silently canonicalized (casing: "vip" → "VIP")
- **unique fuzzy** → resolved and *disclosed*, not asked ("'teresa' → Teresa Alvarez —
  say if I got one wrong"); asking here re-created the v1-plan over-asking problem
- **ambiguous** (two Johns) → asks with the candidates, never silently chooses
- **none** → tags build with a "create it first" note; assignees/inboxes are asked
- an existing workspace entity the user never referred to is still **hallucinated**
  and scrubbed — tools don't widen the provenance gate

The workspace is optional end to end: the eval/CLI path runs without one, and the
no-workspace system prompt is byte-identical (asserted), so all committed eval numbers
remain valid. Live smoke (6 scenarios + 2-turn disambiguation): all behaved to spec on
the first run — transcript: `../eval/runs/entity-smoke-2026-08-09.md`. `serve2.py`
loads the fixture.

**Entity eval slice (v2.6.1, 2026-08-09)**: the smoke test became scored ground truth —
`../eval/entity-eval-set.jsonl`, 10 records run with `cli.py --workspace`, graded on
BOTH the final rule (canonical names must appear in the JSON) and conduct: new
`must_mention` / `must_not_mention` record fields assert transcript behavior (the
two-Johns question, the create-first note, asking instead of inventing). Baseline
7/10 → **10/10** after two extraction fixes the slice caught: ambiguous/unknown
entities were leaving slots null (so the validator asked its generic question instead
of the pick-one), and supported-actions-with-missing-values were misfiled as
"unsupported" — the same wart the teardown's Demo B recorded, now fixed and regression-
guarded. Full sweep after the prompt change: entity 10/10, mt 12/12, core 37/40, ai 12/18.

## Multi-turn eval (v2.5.5, 2026-08-09)

The clarification loop now has permanent, scored ground truth: `../eval/multi-turn-eval-set.jsonl`,
12 scripted conversations across 8 categories (vague openings, drip-fed values, linkage
ambiguity from the rw-039 sim miss, post-completion correction, batched numbered answers,
unsupported-mix, scope confirmation, vague AI asks). Records reuse real prod ideals where
possible. Harness: `cli.py` accepts `{"turns": [...]}` and prints the full transcript;
`run_eval.py --eval-set` plays the turns; `report.py` grades the LAST json block and
reports avg copilot turns + completion. Echo dry-run: 12/12.

The ladder — every fix found by this suite, with cross-suite effects:

| run | mt | what it caught |
|---|---|---|
| v2.5 baseline | 8/12 | — (all 12 completed, avg 2.2 turns, 0 over-asks) |
| v2.5.1 | 10/12 | "emails from x@y" drew `is` in conversation (rule-8 gap) → fix also raised core to 37/40; one AI check over alternatives split into 3 AND'd booleans |
| v2.5.2 | 11/12 | fuzzy adjective ("important client emails") spawned an unasked-for AI variable that survived the literal answer |
| v2.5.3 | 12/12 | placeholder-string runaway ("inbox_name_here…") truncating the JSON — surfaced only after the runner started capturing stderr; + max_tokens & one rescue retry |
| v2.5.4/5 | 12/12 | `variable` field dropped on exists-gates (rule 12 over-taught null); boolean `exists` now normalized to `is true` in the validator (no boolean-exists in the dump — flagged assumption) |

Final: **12/12 strict, 12/12 completed, avg 2.2 copilot turns, 0 redundant questions.**
Honest caveat: mt-005/006 (the linkage-ambiguity pair) pass because the model reads the
cues ("as well", "both must match") correctly, not because the copilot asks — a fully
cue-free drip could still guess. The explicit all-vs-any question remains on Next.

## Closing behavior (v2.6.4, 2026-08-09)

User-reported UX bug: after a rule completed, "that's about it" re-rendered the full
"Here's the automation… Want any adjustments?" pitch verbatim. Fix in three layers:

- extraction gains a `closing` boolean (rule 13): the latest message wraps up and adds
  no rule content;
- **code gate** (`copilot._contributed`): a message containing any rule value cannot be
  a closing, whatever the model says — added after mt-014 caught "use the 'Urgent'
  tag, thanks!" being marked closing on its first run (rule 13's own counter-example);
- rendering: complete+closing → a short wrap-up ("All set — the rule is final…"),
  needs_info+closing → an honest "can't run yet without a bit more" before the
  questions. `respond_structured()` exposes `closing`/`done` for UIs.

Eval: mt-013 (closing) + mt-014 (thanks-with-content guard) → **mt 14/14**. Regression
sweep: core 37/40, entity 10/10 unchanged; ai slice 11/18 — the schema change flipped
two boundary records, rw-042 recovered via a rule-4 trigger example, rw-049 (thank-you-
closer gate grouping) remains a documented **variance cluster** (rw-047/048/049 flip
run-to-run at temperature 0; not chased with more prompt text — see Next).

## Conversational polish (v2.6.5/6, 2026-08-09)

- `intent_summary` re-specified (rule 14): second-person restatement of the goal in
  the model's own words ("You want the Streamliner notification emails closed
  automatically…"), never an echo — the UI leads replies with it, Amplitude-style.
- Rule 2 addition: linkage ANSWERS ("either one is enough" / "both must match")
  restructure the accumulated condition groups. Restored mt-005 after the intent
  change flipped it. mt 14/14, core 37/40, entity 10/10 — all stable.

**The gated AI slice is oscillating with prompt growth** and is now documented as
such rather than chased: 12 → 11 → 12 → 10 → 11 → 10 → 8 over the last seven prompt
versions (v2.4.3 → v2.6.6), while the three pilot-surface suites stayed flat. Every
behavior rule added for the pilot surface dilutes the AI-rule instructions. The
structural conclusion for the eventual merge with the AI-automation project: AI-step
extraction needs its own prompt/pass (or few-shot examples), not more rules in the
shared prompt. The slice remains a canary, not a pilot claim.

## Structured questions (v2.6.7, 2026-08-09)

The validator's planned questions now carry their own answer structure —
`questions_structured`: `{slot, prompt, kind: choice|text, options[], multiple,
allow_other, other_hint}` — because the validator already computed the options (the
two ambiguous Johns, the status enum, the scope split, boolean gates, single-select
labels). Prose questions are derived from the same entries, so the CLI/eval output is
unchanged (mt re-run: 14/14). UIs render choice questions as quick-answer forms; the
contract is that a selection COMPOSES A CHAT MESSAGE (the option's `value` text) —
answers always travel through the conversation, never a side channel, because the
transcript is the engine's only state and the provenance gate's only source.

## Coherence checks + did-you-mean (v2.7, 2026-08-09)

Driven by a real conversation: "also, when it comes from billing@… " merged into the
existing invoice@ rule, producing `From contains invoice@ AND From contains billing@`
— legal by the schema, **unsatisfiable in reality** (one From address), and the
validator accepted it. Two new validator layers, both pure code:

- **Coherence**: AND'd groups constraining the same single-valued header (from,
  from_domain, reply_to, reply_to_domain) with non-nesting values -> a structured
  "should these be two separate automations?" question (never-fires explanation,
  two-automations vs match-either options). Duplicate assign/status actions -> "only
  the last one sticks" question. Nested values ('acme.com' + 'invoice@acme.com') are
  correctly NOT flagged. Verified live: answering "two separate automations" cleanly
  un-merges back to the original rule.
- **Did-you-mean**: scrubbed-but-near-workspace values ('urgnet' -> 'Urgent' scores
  0.833, under the 0.85 auto-resolve bar) become confirm/choice questions via
  `workspace.suggest()` (0.6 floor) instead of open-ended re-asks — in all three typo
  paths: model-normalized then scrubbed, kept verbatim as unknown tag, unknown
  assignee/inbox. Asking is safe where silent typo-correction wouldn't be.

29/29 units; full sweep: core 37/40, mt 14/14, entity 10/10 (ai canary 11/18, in band).

## Connector recipes + Apps panel (v2.8, 2026-08-17)

**Product requirement:** an admin configures an app-based automation from EITHER
the Apps panel or the Automations panel — it's the same underlying flow either
way, so "Make an API call" / connector automations had to become a first-class
action type INSIDE this engine (one schema, one extractor, one validator, one
executor), not a second engine that happens to look similar.

**Single-example scope — read this before adding recipe #2.** Everything below
is built against exactly ONE validated example (Salesforce auto-assign to the
account's CSM) plus one Track A example (viewing Salesforce account/contact
details). No other recipes are stubbed in to make the design look more general
than it is — that would hide, not reveal, what the mechanism actually handles.
What IS meant to be general-purpose, and should not need another architecture
pass when the golden dataset brings more real recipes:

- **The `RECIPES` shape** (`schema.py`): id → app/name/description/chain/
  prerequisites, with an ordered chain of `api_call`/`assign` steps and
  `extract_variables` hand-offs between them. Adding recipe #2 is a data entry
  here, plus a small mock service module if the app is new — see the
  GENERIC/SHAPED-BY-ONE-EXAMPLE comments directly on `RECIPES` in schema.py for
  exactly what does and doesn't generalize yet (only `api_call`/`assign` step
  kinds exist; prerequisites are boolean flags, not configured values).
- **The `connector` action type** (`schema.ACTIONS`): `recipe` (required,
  enum-checked against `RECIPES` — the assign_among precedent: a structural
  choice must be explicit, never inferred) + `test_contact_email` (this
  recipe's ONE setup-time slot, provenance-guarded like any other free-text
  value). Don't assume recipe #2 needs the same single-slot shape.
- **The validator's prerequisite check** (`validator.py`): re-verifies the
  chosen recipe's `prerequisites` against `connected_apps.py`'s fixture —
  the same "never trust the model's own say-so" stance entity resolution
  already gets. Fully data-driven off `recipe["prerequisites"]`.
- **The executor's chain runner** (`executor.py`): template-fills `{{var}}`
  refs, calls the recipe's app's mock service, extracts named variables from
  raw responses, stops CLEANLY (`status: "no_match"`) rather than throwing
  the moment a step can't produce what's needed — the no-CSM case is a real,
  valid outcome, not an error.
- **Track A** (`features.py`, `schema.FEATURES`): enabling an existing App
  feature is NOT an automation (no trigger/conditions/chain) and has no
  Automations-panel equivalent — kept as a genuinely separate, smaller
  mechanism rather than bent into the rule-spec schema to reuse code that
  doesn't fit it.

**Two entry points, one engine:** `serve2.py` (Automations panel) now also
loads `connected_apps.json` so a connector rule built there test-runs
correctly; `serve_apps.py` (new — Apps panel) is scoped to one connected app
and offers both Track A and Track B for it, importing the identical
schema/extract/validator/copilot/executor modules — no forked logic. With
only one app/recipe, "scoped to this app" is trivially true today; the
`serve_apps.py` module docstring says exactly where an `app` filter needs to
be threaded into `extract.build_system()`'s vocab block once a second app
shows up, rather than guessing that shape now from a single data point.

**Testing:** `test_connector.py` covers the five called-for cases —happy path,
CSM-vs-AE role filter (an account with both roles must resolve to the CSM,
never the AE), no-CSM clean failure, provenance rejection, and the downstream
half of no-match escalation — all pure code, no LLM/API key required.
`eval/connector-eval-set.jsonl` has 6 records for the LLM-dependent half
(routing "assign new conversations to the account's CSM" onto the recipe, and
NOT onto it for a different Salesforce action or a different app entirely) —
not runnable in an environment without `OPENAI_API_KEY`/the `openai` package,
which this build's sandbox has neither of; run it via `cli.py`/`run_eval.py`
once a key is available. Regression: `test_validator.py`'s existing suite is
unaffected (56/56 core, 58/58 units before and after — see the eval numbers
posted with this change; the schema-coverage script here is on a version
ahead of the README's original 37/40 snapshot).

## Next

- **Multi-rule sessions** (the real fix behind the coherence questions): the session
  holds a rule list, "also when…" starts rule 2, apply creates them all. Extraction
  schema change -> full sweep + new mt records; UI stacks cards per rule.
- Explicit all-vs-any question when condition groups accumulate across turns with no
  linkage cue (mt-005/006 pass on cue answers today). The rw-047/048/049 grouping
  variance is the same structural problem — a validator-side answer beats more prompt;
  it would now arrive as a structured two-option question for free.
- Dedicated AI-step extraction pass, if/when the AI-automation merge happens (see above).
- Confirm AND-of-OR-groups semantics with engineering (still assumed from data).
- Ask AND-vs-OR when multiple condition groups accumulate across turns without an explicit
  connective (rw-039 sim miss).
- `time_slot`/timezone support on date & time conditions (rw-050 is the driving case).
- Tier-3 judge for the accumulated needs-judge classes: `is`↔`contains` op equivalence
  (rw-010/015/017) and AI encoding equivalence (rw-043).
