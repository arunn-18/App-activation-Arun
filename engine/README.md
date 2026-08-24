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

## Track A extraction routing fix (v2.8.1, 2026-08-18)

A live end-to-end run surfaced a real bug the pure-code test suites above
couldn't catch on their own: `extract.py` had no vocabulary for Track A at
all, so a genuine Track A ask ("set up Salesforce account cards for my
shared mailbox") was forced through the ONLY output shape the model knew —
an automation `rule_spec` — and the copilot dutifully started asking "when
should this run?" for a request that was never an automation.

Fix, in the same spirit as the connector recipe's routing (rule 19): `extract.py`
gained an `app_feature` field (rule 20) the model sets ONLY for asks matching
`schema.FEATURES`, leaving trigger/conditions/actions at their empty
defaults rather than inventing them. `copilot.py`'s `_turn()` now branches
BEFORE the automation validator ever runs: `feature_request_result()`
resolves an `app_feature` ask through `features.py` directly, and
`validator.validate()` — which only understands the rule shape — never sees
it. The UI got a real `FeatureCard` (distinct from `RuleCard`) so this
renders as "app feature enabled/blocked," not a fake WHEN/IF/THEN draft with
holes in it.

`test_track_a.py` (new) pins this down in pure code: `app_feature` must
route to the feature track, never emit a `rule` JSON, never ask an
automation question, and win even if a spec somehow carried stray rule
content alongside it (the mutual-exclusion the model is instructed to keep,
verified independently of whether the model actually keeps it). Full sweep
after the fix: core 56/56, validator units 58/58, connector 30/30 — no
regressions (this suite was superseded by the rebuild below one commit
later, once real product requirements arrived).

## Track A rebuild: a real multi-turn setup flow (v2.9, 2026-08-18)

The v2.8.1 fix above was still wrong in a deeper way — it treated Track A as
a single yes/no check ("are prerequisites met?"). The actual product spec
("Apps Activation Steps: Usecase-wise steps", provided as a CSV) describes
enabling a feature as a real guided flow:

1. **Authentication** — connect the app (a one-time, per-workspace action)
2. **Record-level visibility config** — pick which objects to show, from a
   fixed out-of-the-box list (`schema.ALL_SUPPORTED_OBJECTS`)
3. **Field config - Read** — for each chosen object, pick fields from a
   *live describe call* (`salesforce_mock.describe_fields`, backed by
   `schema.FIELD_CATALOG`) — standard AND custom fields, never a hardcoded
   guess
4. **Confirm & enable**

`engine/features.py` was rewritten around `resolve_setup()`: a
validator.py-style step-by-step resolver (one blocking question at a time,
not up to 3 — this flow is inherently sequential) that walks these four
steps using `feature_setup`, a new accumulated slot group in `extract.py`'s
output (rule 21) filled the same way `condition_groups` accumulates for
automations — re-derived from the WHOLE conversation every turn, not
incremented. `connected_apps.py` gained a real `connect()` action (the
Authentication CTA's mock "OAuth complete" — flips the connected-apps
fixture in place, in-memory for the life of the server process, the same
demo-state pattern as the rule log). The demo fixture (`connected_apps.json`)
now starts **disconnected** by default so the Authentication step actually
shows on a fresh run, instead of skipping straight past it.

`copilot.py`'s Track A branch (`feature_request_result`/`render_feature`)
now carries `progress` (connected? which objects/fields chosen so far?) the
same way `render_structure()` shows partial WHEN/IF/THEN — and the UI's
`FeatureCard` renders that running summary, while the connect/object/field/
confirm QUESTIONS themselves reuse the exact same `QuestionForm` component
the automation flow uses (no new UI question-rendering code needed — the
component was already fully generic on `kind`/`multiple`/`options`).

Scope for this pass, per direct product input: only the first TWO CRM use
cases from the spec (Viewing account & contact details; Smart routing to
right owner — unchanged, it's the existing CSM-autoassign recipe) are
built. Field config - Write, Prefill fields, and Quick Access (listed in the
spec for OTHER use cases — Managing CRM Records, Syncing conversations) are
explicitly deferred, not half-built; `schema.py`'s FEATURES/FIELD_CATALOG
comments say exactly what a future use case needs supplied (real field
names, not invented ones) before it can be added.

`test_track_a.py` was rewritten for the real flow: every step in isolation
(auth gate, object validation against this feature's own choices, per-object
field validation against the mock describe call, confirm), PLUS a full
6-turn simulation through the real `copilot.respond_structured()` pipeline
(only `extract.extract` stubbed) proving turn-over-turn accumulation works —
connect, pick both records, fields for the first, fields for the second,
confirm, enabled. 26/26 passing. Verified live via a browser walkthrough of
the exact same 6 turns against the real UI, real `features.py`, real mock
Salesforce describe calls. Full sweep: core 56/56, validator units 58/58,
connector 27/27 (3 Track A checks moved out to test_track_a.py), track A
26/26 — no regressions.

## Structural split: automation/ and apps/ as peer packages (v2.10, 2026-08-19)

Live testing after the v2.9 rebuild surfaced the real complaint: even with a
proper multi-turn Track A flow, the wire schema was still, in the user's own
words, "the automation schema, with two extra optional fields hanging off the
side." `extract.py` was ONE shared extraction call whose strict JSON schema
carried `trigger`/`condition_groups`/`actions` (automation) AND
`app_feature`/`feature_setup` (Track A) as siblings in the same object —
structurally still one schema pretending to be two, regardless of how much
downstream branching logic (`copilot.py`'s `_turn()`) tried to keep them
apart. That's a real design smell, not a cosmetic one: every future Track A
field would keep landing as an afterthought bolted onto the automation
object, and the two tracks could never evolve independent vocabularies
without fighting over one shared `strict` schema.

Fix: automation and Track A are now genuine peer Python packages,
`engine/automation/` and `engine/apps/`, each with its own `schema.py`,
`extract.py` (own strict JSON schema, own SYSTEM prompt, own vocabulary —
neither imports the other's), and their own resolver (`automation/validator.py`
/ `apps/setup.py`) and, for automation, `executor.py`. Shared infrastructure
both tracks genuinely need — `connected_apps.py` (prerequisite state used by
both a connector recipe's prerequisites and a Track A feature's) and
`salesforce_mock.py` (the mock service both a connector chain step and a
Track A describe-fields call use) — stays at the top level as real shared
modules, not duplicated into either package.

**`router.py` (new):** the FIRST model call of every turn, classification
only. It decides `track` ("automation" | "app_setup") from the WHOLE
conversation history, re-derived fresh each turn and sticky once established
— BEFORE either track's extraction schema is even loaded. `copilot.py` calls
`automation.extract.extract()` or `apps.extract.extract()` depending on what
the router said; neither extractor has ever heard of the other's fields.
`capability_question`/`no_intent` are read-only classifications that ride
alongside `track` (mirroring the old single-call design) so a capability
question or a gibberish turn never erases whatever progress the real track
already has.

**Wire contract preserved on purpose:** `copilot.respond_structured()`'s
output shape — `status`/`track`/`feature_request`/`spec`/`draft`/
`questions_structured`/etc. — is unchanged, so the UI (`ui/lib/api.ts`,
`RuleCard`, `FeatureCard`) needed zero edits. The fix was entirely about how
the ENGINE reaches that shape (two independent schemas instead of one
shared one with a branch), not about what it hands the UI.

**Testing:** all three pure-code suites were updated for the new import
paths and package-scoped monkeypatches (`test_track_a.py` now stubs
`router.classify` AND `apps.extract.extract` separately, matching the real
two-call pipeline) and re-run clean: validator 56/56 core + 58/58 units,
connector 27/27, track A 26/26 — no regressions. `ui/scripts/sync-engine.sh`
now vendors `automation/` and `apps/` as real subpackages (not flattened)
and its self-import check verifies every module inside each, the same
denylist-not-allowlist guarantee it already had for the top level.

## Dynamic connector plans + Track A inbox scoping (v2.11, 2026-08-20)

Two product asks after the v2.10 restructuring: more automation/App use
cases, and — the harder one — "you have still not figured out the flow for
finding the APIs by yourself and using them accordingly in the automations
to get to the usecases user is asking for." Given the choice between
hand-authoring more `RECIPES` entries or a genuine dynamic-composition
capability, the direction chosen was the latter, WITH explicit guardrails
(the user's own follow-up ask) — a model composing its own API call
sequence at runtime is a real capability increase, not something to ship
without a safety design.

**Track A:** the final "Enable?" step (a plain yes/no CTA) is now a
multi-select of the workspace's shared inboxes — naming inbox(es) IS the
enable action, since a feature like account/contact cards is meaningfully
scoped per inbox, not a single global switch. `apps/setup.py`'s step 4
replaced the old boolean `confirm` slot; `apps/extract.py` captures
whichever inbox names the user answers with; `FeatureCard.tsx` and
`copilot.render_feature()` show an "ENABLED FOR" line once chosen.

**Track B — the harder half — dynamic connector plans.** `RECIPES` stays
exactly what it was: a small set of hand-vetted, fully-tested chains — the
fast, fully-trusted path. New alongside it: when a Salesforce-connector ask
doesn't match any RECIPES entry but IS the same *shape* (look up some
Salesforce data about the sender's account/contact, then assign or tag the
conversation based on it), the model can compose its OWN chain at
extraction time instead of the request being escalated straight to
`unsupported_requests`.

- **`salesforce_schema.py`** (new, top-level, shared): the closed CRM object
  catalog — Contact/Account/AccountTeamMember/Opportunity/Case, their real
  field names, and (critically) which fields are marked `assignable_fields`
  / `taggable_fields` — a deliberate claim about which values make sense as
  a connector's terminal action, not an accident of a field merely existing.
- **`salesforce_mock.py`** gained generic `query()`/`describe_object()`/
  `list_objects()` primitives — every hand-written op (`find_contact_by_email`,
  `get_account_team_csm`, ...) is itself expressible as one `query()` call
  with the right filter; they stay as named wrappers only because the
  existing recipe and its tests already refer to them by name.
- **`automation/planner.py`** (new): read-only exploration tools
  (`list_objects`, `describe_object`) the extractor calls before proposing a
  plan — mirrors `workspace.py`'s existing TOOLS/dispatch pattern exactly.
  Wired into `automation/extract.py`'s SAME bounded tool-calling loop
  (previously gated on a workspace being connected; these tools now run
  regardless, since they describe Salesforce's own schema, not workspace
  entities).
- **`automation/extract.py`** rule 19b: a connector action's `custom_plan` is
  an ordered list of `{object, where, extract_variables}` lookup steps (built
  as arrays of `{variable, field}` pairs, not a `{name: field}` map — OpenAI
  strict-mode JSON schema can't express an arbitrary-key object) plus one
  `{kind: assign|add_tag, ...}` terminal — never both `recipe` and
  `custom_plan` on the same action, and never a forced plan when no
  plausible chain exists (falls back to `connector_other`, same honest
  escalation rule 19 already had).

**The guardrails** (`automation/plan_validator.py`, new) — a model-composed
plan gets NO benefit of the doubt, unlike a RECIPES chain a human already
proved correct:
- every object/field referenced must be real, per `salesforce_schema.py`
- every step's filter value must chain from the seed context or a variable
  an EARLIER step actually extracted — never a forward/undefined reference
- the terminal's value must come from a field explicitly marked usable for
  that action kind — a real field holding a string (e.g. `Case.Subject`) is
  NOT automatically legal as an assign/tag source
- bounded to `MAX_PLAN_STEPS` (4)
- **a stricter completeness bar than a fixed recipe gets**: `automation/
  validator.py`'s connector block actually EXECUTES a structurally-valid
  plan against the mock as part of validation, and only counts it toward
  `status: complete` if that run comes back `"ok"` — a `no_match` is a
  legitimate outcome for a RECIPES chain (already proven correct once by
  `test_connector.py`) but NOT proof enough for a plan that's never
  succeeded before. `executor.py` itself needed no new step kinds beyond
  `add_tag`; `_fill()`/`_unresolved()` learned to recurse into the plan's
  structured `where`-clause args, and a validated plan converts
  (`plan_validator.to_chain()`) into the exact same `{"app", "chain"}` shape
  `run_chain()` already ran a RECIPES entry through.

**Two use cases prove genericity** (no RECIPES entry involved for either):
assign to the Account's Owner instead of the CSM (2-step: Contact ->
Account), and tag the conversation with an open Case's priority (2-step:
Contact -> Case). Both run end-to-end against the mock fixture
(`salesforce_fixture.json` gained `opportunities`/`cases` tables and a
per-account `owner_email`, including a real entry for
`arunnayak.b@grexit.com`).

**Testing:** `test_connector_planner.py` (new, 18 cases, pure code, no LLM)
covers every guardrail rejection individually, both dynamic use cases
end-to-end (structural validation -> prerequisite check -> real test-run ->
`complete`), the stricter no-proof-no-complete bar, prerequisite gating on a
dynamic plan same as a fixed recipe, the fallback question when neither
`recipe` nor a valid `custom_plan` is present, and `copilot.py`'s rendering
(draft text, exported JSON's `custom_plan`/`assigns_to`/`tags_with`,
`connector_test_run`) for a plan-based action. The actual tool-calling
composition step (a live model turning "assign by Account Owner" into a
correct plan) is, like the fixed recipe's own routing, not verifiable in
this sandbox (no `OPENAI_API_KEY`) — everything downstream of "the model
proposed this plan" is. No regressions: validator 56/56 core + 58/58 units,
connector 27/27, track A 29/29.

## Onboard-any-app foundation: unified catalog, capabilities 4/5/7, mapping explanation (v2.12, 2026-08-21)

The ask: build the base so a NEW Marketplace app onboards with config
changes, not engine code — defining its auth, its capabilities, and its
API surface — and cover the full requested conversational flow: identify
the usecase, map it to the catalog, SAY the mapping out loud, decide
Track A/B/not-possible, help with setup, and offer to test on a real
conversation. Six numbered capabilities were named explicitly: (1) auth,
(2) record-level config, (3) field config for viewing, (4) field config
for writing, (5) native app-action automations, (6) API-composed
automations (already built in v2.11). This pass adds 4, 5, 7 (the
mapping-explanation step), and the foundation that makes onboarding app #2
genuinely config-only.

**`app_catalog.py` (new, top-level, shared) — the unification.** Before
this, the same kind of information was described TWICE with no shared
source: `apps/schema.py`'s `FIELD_CATALOG` (display names, for Track A's
view picker) and `salesforce_schema.py`'s `OBJECTS` (API names +
assignable/taggable flags, for Track B's planner). Onboarding app #2 would
have meant writing both shapes by hand for it. Now one file describes each
field once, with explicit flags (`view`/`write`/`custom`/`assignable`/
`taggable` — never inferred from type alone), and both `FIELD_CATALOG` and
the new `WRITABLE_FIELD_CATALOG` derive from it (`field_catalog()`/
`writable_field_catalog()`), as does `salesforce_schema.OBJECTS`
(`api_objects()`). Verified byte-for-byte identical to the old hardcoded
values (same labels, same order, same assignable/taggable sets) — zero
behavior change to the existing Track A flow, the one non-negotiable
guardrail on this whole pass.

**Capability 4 — write-usecase field config** (`salesforce_create_contact`,
"Managing CRM Records from Hiver"'s create-a-Contact slice): a Track A
feature now carries `kind: "view"` (default) or `"write"`.
`apps/setup.py`'s field-config step branches on it — a write-kind feature
reads `WRITABLE_FIELD_CATALOG` via its own `describe_writable_fields()`
mock call, with its own question wording ("fill in when creating one" /
"create" vs "show"). A genuinely separate branch, not a parameter tweak —
every existing Track A test still passes unchanged, plus 5 new ones
proving the write branch is real (e.g. Contact Email is viewable but not
writable, so it's absent from the write picker).

**Capability 5 — native app-action automations** (`clickup_create_task`):
a connector action now has THREE mutually-exclusive mechanisms, in order
of trust already earned — a hand-vetted `RECIPES` chain, a native action
block (new), or a dynamically-composed `custom_plan`. Native actions are
Hiver's own pre-built integration (no chain, no API composition — "fire
this"). `automation/schema.py`'s `NATIVE_ACTIONS` registry is entirely
data-driven (`op` + `args` mapping the service's own param names to the
connector's two generic slots, `target_name`/`title_hint`);
`executor.run_native_action()` needs no per-action code.
**`clickup_mock.py` is the SECOND real app in this engine** — proving
capability 5 generalizes past Salesforce, not asserting it in comments.
Onboarding it needed one `connected_apps.json` entry, one `NATIVE_ACTIONS`
entry, and this one small mock module — no engine code changed. Along the
way, fixed a real pre-existing bug: `_render_test_run` crashed (KeyError)
on an `add_tag`-terminal result (the v2.11 "tag by Case priority" plan),
since it unconditionally read `.final.target`.

**Capability 7 — test on a real conversation.** Instead of asking an admin
to type an arbitrary test email, `mailbox_lookup.py` offers REAL
conversations from the demo mailbox whose sender is a known Salesforce
contact. Track B's `test_contact_email` question is now a CHOICE of real
conversations with a free-text fallback (same slot, same requiredness,
only the presentation changed). Track A gets a genuinely new courtesy —
`apps/setup.py`'s `preview_feature()` actually queries the mock for a named
real contact and shows the REAL field values, never a placeholder; never
blocks completeness, and explicitly skipped for write-kind features (there's
no existing record to preview yet). Surfaced this fixed a real honesty gap:
Track A's catalog always listed Contact Name/Phone/Role as viewable, but
the fixture had no such data — now every fixture contact has real values.

**The usecase-to-capability mapping explanation** (the missing conversational
step): `copilot._mapping_explanation()` composes ONE sentence — "you want X,
I can do that via Y, here's how" — entirely from the matched capability's
own name/description, the same "answer only from schema.py" discipline
`docent.py`'s capability answers already follow. Fires exactly once per
conversation (`_turn()`'s `is_first_turn` gate: no assistant message in
history yet), covering all three Track B mechanisms and Track A features;
silent when nothing has matched, leaving the existing unmappable/unsupported
escalation to carry the "not possible" case.

**Testing:** three new suites (`test_native_action.py` 10, `test_mapping_
explanation.py` 7, `test_real_conversation.py` 12), all pure code, no LLM —
same reasoning as every other capability suite here: which capability a
live model picks isn't verifiable in this sandbox; everything downstream
of "the model matched this" is. No regressions across the full run:
validator 56/56 core + 58/58 units, connector 27/27, track A 34/34,
connector planner 18/18. `ui/` (FeatureCard.tsx, RuleCard.tsx, lib/api.ts)
updated for every new field on both wire contracts and typechecks clean
(`npx tsc --noEmit`).

## Live-testing fixes + connector connect-fix + ClickUp field expansion + inbox scoping + capability 4's second app (v2.13, 2026-08-24)

The ask this pass: a round of live testing against v2.12 surfaced real gaps
no eval record had exercised — a UI crash, a stale router rule, a
prerequisite an admin could see but never fix, and a native action that
only covered two of ClickUp's real task fields. Each is fixed at its root
cause, not patched at the symptom, plus the two structural asks that came
out of that testing: every automation must now say which shared inbox(es)
it applies to, and capability 4 (write-usecase field config) needed a
SECOND real app to prove it, not just Salesforce.

**RuleCard crash on a bare capability question.** `copilot._turn()` was
labeling an unmatched `app_setup` turn `"track": "automation"` while handing
back an apps_extract-shaped spec with no `trigger`/`actions` — one track's
shape leaking into the other's consumer. Fixed by normalizing to the same
empty automation shape a fresh automation turn already gets.

**Router disambiguation rewrite.** "Create a Contact from Hiver" was
misrouted to Track B: a stale DISAMBIGUATION rule ("creating is automation,
even if it mentions the app") predated capability 4 and contradicted the
router's own FEATURES vocab. Rewritten around the real signal — does an
agent invoke this by hand once enabled (`app_setup`), or does it fire
automatically on a trigger (`automation`) — using `salesforce_create_contact`
as the worked example. A separate, unrelated symptom of the same report
(a suggestion chip template, `"Set up: X — Y"`, reading as automation-shaped
to the classifier) was fixed by using the bare capability name instead.

**Connector automations can now actually fix their own prerequisite gate.**
`connected_apps.connect()` had only ever been called from Track A's
`apps/setup.py` — a connector action's prerequisite check in
`automation/validator.py` could tell an admin ClickUp wasn't connected, but
offered nothing to click, a dead end live testing caught immediately. Fixed
with a new `connect_requested` slot and a shared `_check_connector_
prerequisites()` helper (recipe/native/custom_plan mechanisms all route
through it): when a one-click fix exists (`connected_apps.PREREQUISITE_
ACTIONS`), it's now a real "Connect ClickUp" choice question, same shape
Track A's own connect step already offered; when none exists (e.g.
`account_team_enabled`), it stays an honest static error rather than a fake
CTA.

**ClickUp native action expanded to all 6 real task fields**, and bundled
into ONE form. `clickup_create_task` covered only List/Title; live testing
asked for the whole task-creation block — Description, Assignee, Due date,
Priority added (all optional; `clickup_mock.create_task()` never fakes an
unset one). Asking for all 6 sequentially would have meant 6 back-and-forth
turns, so `validator.py` gained a new structured-question `kind: "form"` —
one UI block bundling every field (required ones flagged, `priority_hint`
offered as a real enum choice, not free text) — submitted as ONE chat
message that still round-trips through the same provenance-guarded
extraction pipeline. `QuestionForm.tsx` renders `kind: "form"` questions via
a new dedicated `FieldBlockForm` component, outside the existing
one-question-at-a-time `Questionnaire` pagination.

**Every automation now names its shared inbox(es).** A new top-level
`enabled_inboxes` slot, required the moment a real workspace is loaded
(`ws is not None`) — skipped entirely for eval/CLI runs, since `ws=None`
there — the direct Track B analogue of Track A's own step 4 ("ENABLED
FOR"). Blast radius turned out much smaller than first estimated: most
connector tests pass `apps_ws=` (connection state) but not `ws=` (the
entity/inbox fixture), so only `test_validator.py`'s own "complete" fixtures
needed `enabled_inboxes` added.

**Extraction vocab is now genuinely scoped per app**, closing a TODO
`serve_apps.py`'s own docstring had carried since there was only one app to
scope against. `automation/extract.py`'s `_vocab_block(app=None)` filters
`RECIPES`/`NATIVE_ACTIONS`/the connector action's own `recipe=` enum/the
Salesforce-only custom_plan objects line by app; threaded through
`copilot._turn()` → `respond()`/`respond_structured()` → `serve_apps.py`'s
`/chat` handler, which now actually passes `app=app`. `app=None` (the
general Automations page) is verified byte-identical to the old unscoped
behavior.

**Capability 4's second app: `clickup_create_task_from_hiver`.** The
Salesforce write feature was the only proof capability 4 generalized past
one app; live testing asked for the same "create X from a conversation"
flow for a ClickUp task. `app_catalog.py` gained a `clickup` → `Task` entry
(6 fields, `write: True`, api names matching `clickup_mock.create_task()`'s
own kwargs so `field_by_label()` needed no adapter); `apps/setup.py`'s
`resolve_setup()` needed only a small `_WRITABLE_CATALOG_BY_APP`/`_CREATE_
OPS` config table (catalog+describe-call, create-op dispatch) in place of
its two Salesforce-only hardcoded lines — the object-picker and
`<object>_fields` slot-derivation logic underneath were already fully
app-agnostic. `clickup_mock.describe_writable_fields()` mirrors the
Salesforce version exactly. This is a genuinely separate mechanism from
`clickup_create_task` (the native ACTION above) — one is Track A (an agent
manually creates one task from an open conversation), the other is Track B
(an automation fires on a trigger, no human in the loop); same app, same
underlying mock call, deliberately different ids.

**Testing:** no regressions — every pre-existing assertion still passes,
plus additive coverage for each fix above: `test_track_a.py` 45/45,
`test_connector.py` 29/29, `test_connector_planner.py` 18/18,
`test_native_action.py` 24/24 (6-field form, `connect_requested`,
app-scoped vocab), `test_validator.py` 56/56 core + 62/62 units
(`enabled_inboxes`), `test_real_conversation.py` 23/23 (ClickUp write
feature end to end), `test_mapping_explanation.py` 7/7 unchanged. `ui/`
(`QuestionForm.tsx`'s form-question split, `RuleCard.tsx`'s "ENABLED FOR"
row, `lib/api.ts`'s new field/type additions) typechecks clean
(`npx tsc --noEmit`).

## Discovery's feature-request offer + self-serve remediation + example phrasings (v2.14, 2026-08-24)

Prompted by a separate, business-level "Apps Activation" PRD (289 onboarded
UGs, 83 active, a 28% activation rate) describing a fuller Discovery →
Guided setup → Live validation → Team rollout flow. A gap analysis against
this engine found most of Guided setup and Live validation already built
(this is exactly what capabilities 1-7 above already do); this pass closes
the highest-confirmed gaps on the two apps that already exist (Salesforce,
ClickUp) — deliberately NOT onboarding a third app yet, NOT making
live-validation a blocking gate, and NOT building real production
activation, real Amplitude/ClickUp-Jira wiring, or team rollout, all
confirmed out of scope for this pass.

**Discovery: "no match → log a feature request?"** Scoped exactly to the
source PRD's own Escalation Trigger table row — `unmappable` specifically
(a genuinely novel ask), not `unsupported_requests` (an already-categorized
gap like custom fields; re-logging those would be noise, not a demand
signal). `copilot._apply_feature_request_offer()` runs at the end of
`_turn()`, uniformly for both tracks (Track A's own unmappable asks reach
it via the same no-match reshape that already normalizes Track A into
Track B's empty spec shape). A new `feature_request_requested` slot
(boolean|null, three-state: unanswered/yes/no) on both extract schemas
mirrors `connect_requested`'s own persistence rule. Logging is EXPLICIT —
a real "Log this as a feature request?" yes/no choice question, rendered
by the SAME `QuestionForm` component every other choice question already
uses, no new UI needed — never automatic just because something didn't
match. New `feature_requests.py` (in-memory, deduped by `(app, request)`)
and `analytics.py` (`EVENTS` names all six events the source PRD specifies;
only `FEATURE_REQUEST_LOGGED` is actually wired — the other five need their
own scoped pass, flagged honestly rather than half-built silently) are
local stubs — no real ClickUp/Jira/Amplitude destination exists in this
repo, same "mock it, never fake it" discipline `connected_apps.json`
already holds itself to.

**Self-serve remediation for a non-one-click prerequisite.** Before this,
`account_team_enabled` (Salesforce's Account Team/CSM setup, which has no
mocked "enable" action) produced an honest but dead-end error — it NAMED
the gate but never said how to clear it. New `connected_apps.
PREREQUISITE_REMEDIATION`/`remediation_for()` supplies real fix-it
instructions, threaded into both `automation/validator.py`'s
`_check_connector_prerequisites()` and `apps/setup.py`'s own auth-step
error branch — one dict, both tracks, same "shared vocabulary lives in
connected_apps.py" precedent `PREREQUISITE_LABELS`/`PREREQUISITE_ACTIONS`
already set.

**Knowledge-layer metadata: example phrasings.** `apps/schema.py`'s
`FEATURES` entries gained `example_phrasings` — real asks each feature
actually matches, reused (never re-invented) by `docent.py`'s capability
answers. Surfaced a real pre-existing gap along the way: the "Salesforce
integration" capability answer filtered to `app == "salesforce"` only,
so it had never once mentioned ClickUp's own Track A feature
(`clickup_create_task_from_hiver`) despite it existing since the previous
phase — fixed by dropping the filter now that there's a second app to
name. A "known error codes" analogue for Track B (RECIPES/NATIVE_ACTIONS)
was investigated and deliberately NOT built: every mock create op
(`salesforce_mock.create_contact`, `clickup_mock.create_task`) "always
succeeds" — there is no real API integration to fail with a real error
code yet, so a `known_errors` dict would have had to invent codes with
nothing real behind them. Blocked on real (non-mock) API clients existing
first, per this file's own long-standing out-of-scope note.

**Testing:** new `test_feature_request_offer.py` (21/21) — the offer/log/
decline/dedupe flow driven through the real `copilot.respond()`/
`respond_structured()` pipeline (router/extract stubbed, same discipline as
every other suite here), the remediation text reaching both tracks' error
paths, and the docent capability-answer wiring. No regressions across all
8 suites (229 unit cases total). Also shipped alongside this phase: a
golden eval set for Track A capabilities and the router boundary between
tracks (`eval/apps-eval-set.jsonl`, 12 records, its own small grading
harness) — see `eval/README.md`'s "Apps set" section; this closed a real
coverage gap where every prior eval set only ever exercised Track B.
`ui/lib/api.ts`'s `TurnState` and `RuleCard.tsx` updated for the new
`feature_request_offer` field; `npx tsc --noEmit` clean.

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
