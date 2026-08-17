# Automation Copilot v2

An AI assistant that turns plain-English requests into [Hiver](https://hiverhq.com) automation
rules (trigger → conditions → actions) — built as a learning project, rebuilt from scratch
around one idea:

> **The model only extracts. The code decides.**

v1 was a single prompt asked to understand, validate, clarify, and answer all at once. It
worked until it didn't: given a vague request, it would eventually **invent** a tag name or
assignee (usually leaked from its own few-shot examples), and three rounds of increasingly
stern prompt rules could not stop it. v2 splits the job so that failure is structurally
impossible: an LLM fills out a strict form, and a deterministic validator — not the model —
decides what's legal, what's missing, what to ask, and when the rule is done.

## What's in this repo

```
├── engine/            the v2 copilot
│   ├── schema.py         legal vocabulary: 7 triggers, 16 condition properties (+ per-
│   │                     property operators, incl. ai_variable), 7 AI variable types,
│   │                     10 actions (+ required params). Grounded in a 90-day dump of
│   │                     real production automations.
│   ├── extract.py        the only LLM call: conversation -> partial rule spec (strict
│   │                     structured output; unknown slots stay null; unsupported asks
│   │                     listed, never faked)
│   ├── validator.py      pure code: enum/operator legality, trigger x condition
│   │                     compatibility, required params, scope, and PROVENANCE — every
│   │                     free-text value (tag, person, keyword) must appear in the user's
│   │                     own words, or it's scrubbed and re-asked
│   ├── workspace.py      entity resolution against a workspace fixture (workspace.json):
│   │                     LLM lookup tools + the code-side re-verification of every model
│   │                     lookup ("the model may look things up, code re-verifies")
│   ├── copilot.py        turn loop + rendering: draft with ⟨required⟩ holes -> up to 3
│   │                     planned questions per turn -> final WHEN/IF/THEN + machine JSON
│   ├── serve2.py         chat UI (http://127.0.0.1:8001)
│   ├── cli.py            stdin -> stdout single turn (eval adapter)
│   ├── simulate.py       multi-turn self-play: a simulator LLM plays the admin (knows the
│   │                     target rule, opens vague, answers only what's asked, reviews the
│   │                     result); deterministic grader judges accuracy, LLM judge scores
│   │                     conversation quality
│   └── test_validator.py schema coverage (all 40 core eval records must validate) + units
│
├── eval/              the measurement system
│   ├── real-world-eval-set.jsonl   105 eval records mined from REAL production automations
│   │                               (anonymized). Each = a hand-written plain-English ask +
│   │                               the actual rule an admin built as ground truth, tagged
│   │                               with scope_flags so the supported-surface decision stays
│   │                               a scoring-time filter
│   ├── grader.py                   canonicalize both vocabularies -> per-slot diff
│   │                               (trigger / conditions / actions / ai_extract)
│   ├── run_eval.py                 capture-only runner (echo / any CLI / OpenAI prompt)
│   ├── report.py                   scoreboard: strict match, slot table, slices, over-asking
│   │                               counter, failure dump, needs-judge list
│   ├── build/                      reproducible mining pipeline (dump -> candidates ->
│   │                               authored annotations -> eval set)
│   └── runs/                       every run + report ever taken, including the sim
│                                   transcripts — the full audit trail of the numbers below
│
├── automation-copilot-one-pager-2026-07-12.md      product one-pager
├── competitor-study-ai-automation-building-2026-07-12.md
├── call-prep-design-review-2026-07-20.md
├── next-version-scope.md                            deferred items from v1
└── rule-menu.md
```

The v1 prototype (prompt-engineering approach, golden dataset, its own serve UI) lives
outside this repo; the eval baseline numbers below were measured against it.

## The results

Single-turn extraction, 40 core-scope real-world records, strict full-rule match:

| engine | strict | trigger | conditions | actions | over-asks |
|---|---|---|---|---|---|
| v1 (prompt engine, baseline) | 27/40 | 88% | 72% | 100% | 0 |
| v1.1 (ask-first prompt fixes) | 28/40 | 95% | 72% | 100% | 0 |
| v2.3 | 36/40 (90%) | 98% | 92% | 100% | 0 |
| v2.4.3 (+ai_extract) | 36/40 (90%) | 98% | 92% | 100% | 0 |
| **v2.5.4 (this repo)** | **37/40 (92%)** | 98% | 95% | 100% | 0 |

AI extraction (v2.4, 2026-08-09): the AI step (`ai_extract` variables, `ai_variable`
gating conditions, `{{variable}}` note templates) is now in the supported surface —
275 prod automations use it. On the 18-record `uses_ai` slice: **12/18 strict, 12/16
(75%) of supported-scope records** (2 need custom fields, still out of scope). AI
variable names/descriptions are graded name-agnostically — see `engine/README.md`.

Entity validation (v2.5, 2026-08-09): extraction can call workspace lookup tools
(`find_user`, `list_tags`, `list_inboxes`) to canonicalize names, and the validator
re-verifies every lookup from the user's own words — exact matches canonicalize,
unique fuzzy matches resolve with disclosure, ambiguous ones ask (two Johns), unknown
tags get a "create it first" note. Workspace-less runs are byte-identical, so eval
numbers are unaffected — see `engine/README.md`.

Entity eval slice (v2.6.1, 2026-08-09): `eval/entity-eval-set.jsonl`, 10 records graded
on the final rule AND transcript conduct (`must_mention`/`must_not_mention`): **10/10**,
after the slice caught two real extraction bugs (null slots on ambiguous entities;
supported-but-valueless asks misfiled as unsupported). Full board at v2.6.1:
**entity 10/10 · multi-turn 12/12 · core-40 37/40 · uses_ai 12/18.**

Production coverage (2026-08-09): the v2.6.1 surface can fully build **91.8% of the
3,892 organic automations** real admins created in the 90-day window (82.4% of tenants
completely covered). Biggest remaining blockers, by measured demand: saved-list
operators (`is_present_in`), custom fields — not connectors (0.8%). Method + unlock
table: `eval/coverage-2026-08-09.md`, reproducible via `eval/build/coverage.py`.

Multi-turn self-play (10 episodes, vague opening, simulator-as-admin):
**10/10 completed, 9/10 strict match, avg 2.9 copilot turns, 0 redundant questions.**

Multi-turn eval (v2.5.5, 2026-08-09): the clarification loop now has scored ground
truth — `eval/multi-turn-eval-set.jsonl`, 12 scripted conversations (vague openings,
drip-fed values, linkage ambiguity, corrections, batched answers): **12/12 strict,
avg 2.2 copilot turns, 0 over-asks**, after a 5-iteration ladder (8→12) whose fixes
also raised core-40 to 37/40. See `engine/README.md` for the run-by-run story.

Remaining known misses are documented, not hidden: 3 `is`↔`contains` operator equivalences
(needs an LLM judge to adjudicate), 1 ambiguous any-direction trigger, and 1 AND-vs-OR
linkage guess when conditions arrive across separate turns (should become an explicit
question). See `engine/README.md` for the full run-by-run history, including the failures
each iteration caught — the 0/40 grader-vocab run and the 16/40 over-asking run are part of
the story.

## Why the eval set is the interesting part

Most copilot evals are hand-written and test what the author imagined. This one is mined
from 6,412 real production automations (90-day window): stratified 105 records across the
real distribution — keyword taggers, sender routing, follow-up nudges, AI classification,
connectors — with the actual admin-built rule as ground truth and PII anonymized
(domains → `company-NN.example`, personal addresses → `personNN@`). Real admin *mistakes*
are preserved and flagged (`notes`), because the extraction target is what the admin built.
Full provenance and method: `eval/README.md`.

## Run it

Needs Python 3.9+, an OpenAI API key, and `pip install openai` (plus `pandas` only for
re-mining the eval set from a dump).

```bash
export OPENAI_API_KEY=sk-...        # engine/extract.py also reads a sibling .env if present

# chat UI
cd engine && python serve2.py       # -> http://127.0.0.1:8001

# tests (no API calls)
cd engine && python test_validator.py
cd eval   && python grader.py --self-test

# single-turn eval
cd eval && python run_eval.py --engine command \
    --cmd "python $(pwd)/../engine/cli.py" --scope core
python report.py runs/<run>.jsonl --failures

# multi-turn simulation (~90 API calls)
cd engine && python simulate.py
```

Note: `extract.py` currently resolves the API key from `../automation-copilot/.env`
(the v1 project's location on the original machine); set `OPENAI_API_KEY` in the
environment or adjust `load_env()` when running elsewhere.

## Data & privacy

- The raw production dump is **not** in this repo and must never be committed.
- The eval set is anonymized (emails/domains/personal local-parts), but some free-text
  condition values from real automations remain (e.g. person names inside subject-line
  matchers). **Keep this repo private**; a public release would need a second scrub pass.
- `eval/runs/` contains model outputs only — no customer data beyond the anonymized values
  already in the eval set.

## Design decisions worth knowing

1. **Provenance over politeness**: the validator rejects any free-text value that doesn't
   appear in the user's own messages. This single rule killed the hallucinated-tag failure
   class that prompt engineering could not (3 documented attempts in v1).
2. **Meta-language guard**: "match on specific senders" is a mechanism, not a value —
   a blocklist keeps echoed question-language from becoming rule content (found by the
   simulator, day one).
3. **Assumptions are disclosed, not asked**: trigger defaults to "new inbound conversation"
   when unstated (82% of production rules) and the draft says so — asking about it made the
   first v2 run over-question on 13/40 fully-specified requests.
4. **Runner and grader are separate** so grader fixes never re-cost API calls, and every
   run file carries engine/model/prompt-sha for comparability.
5. **Condition semantics** (groups AND'd, within-group OR'd, values any-of) are inferred
   from production data and still await engineering confirmation — flagged everywhere they
   matter.
