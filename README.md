# App Activation

An engine that turns plain-English requests into either an existing Hiver
**app feature** (Track A — enable once per workspace, no trigger) or a
**Hiver automation connected to a real app** (Track B — a trigger +
conditions shell around a connector action). Built around one idea carried
over from the general automation-copilot project this engine grew out of:

> **The model only extracts. The code decides.**

An LLM fills out a strict form; a deterministic validator — never the
model — decides what's legal, what's missing, what to ask, and when a
feature or rule is done.

## Charter (2026-08-27): App Activation only

Every automation this engine builds now has to touch a real app via a
connector action (a native action block, a hand-vetted recipe, or a
composed lookup) — see `engine/copilot.py`'s own scope gate
(`test_app_scope.py` locks it in). Generic Hiver actions (tag, assign,
status, note, reply, notify, move inbox) are still real and still combine
with an app action in the same rule, but none of them is something this
engine builds on its own anymore. This repo's earlier, broader scope — any
Hiver automation, with or without an app action — moved to `legacy/`; see
`legacy/README.md` for what's there and why.

## Start here: the schema

The fastest way to understand what this engine can build is to read the
two schema files directly — every capability traces back to one of these,
and nothing here is invented by the model:

- **`engine/apps/schema.py`** — `FEATURES`: Track A capabilities (an
  existing app feature an admin enables once per workspace — view or
  write a record, no trigger involved).
- **`engine/automation/schema.py`** — `TRIGGERS`/`CONDITION_PROPERTIES`/
  `ACTIONS` (the generic rule-building vocabulary) plus `RECIPES` and
  `NATIVE_ACTIONS` (the two hand-vetted connector mechanisms) — see
  `ACTIONS["connector"]`'s own comment for the third, model-composed
  mechanism (`custom_plan`, validated by `automation/plan_validator.py`).
- **`engine/app_catalog.py`** — the single per-app object/field catalog
  BOTH schemas above derive from; onboarding a new app's objects/fields
  means editing only this file.

`PRD.md` covers the product framing (capability catalogue, guardrails,
open questions) in more depth; `engine/README.md` is the dev changelog
(every phase, in order, including the live-testing bugs each one fixed).

## Repo structure

```
├── engine/                      the App Activation engine
│   ├── router.py                  1st call each turn: classifies track
│   │                               (automation | app_setup) before either
│   │                               package's schema even loads
│   ├── app_catalog.py              THE single per-app object/field catalog
│   │
│   ├── automation/                Track B: per-conversation automations
│   │   ├── schema.py                 triggers, conditions, actions,
│   │   │                             RECIPES, NATIVE_ACTIONS
│   │   ├── extract.py                2nd LLM call — automation-only wire
│   │   │                             schema; routes to recipe |
│   │   │                             native_action_id | custom_plan |
│   │   │                             unsupported
│   │   ├── planner.py                read-only schema-exploration tool
│   │   │                             calls feeding a model-composed
│   │   │                             custom_plan
│   │   ├── plan_validator.py         guardrails for a composed plan: real
│   │   │                             object/field refs only, no forward
│   │   │                             references, assignable/taggable-only
│   │   │                             terminals
│   │   ├── validator.py              pure code: provenance, entity
│   │   │                             resolution, question planning,
│   │   │                             the 4-way connector branch
│   │   └── executor.py               runs a recipe's/plan's chain, or a
│   │                                 native action, for real (mocked)
│   │
│   ├── apps/                      Track A: configuring an existing app
│   │   │                          feature (no trigger/actions)
│   │   ├── schema.py                 FEATURES (kind: "view"|"write")
│   │   ├── extract.py                2nd LLM call — app-setup-only wire
│   │   │                             schema
│   │   └── setup.py                  pure code: resolve_setup() — auth ->
│   │                                 objects -> fields -> inboxes ->
│   │                                 Prefill Fields -> Quick Access;
│   │                                 preview_feature()/test_create()
│   │
│   ├── connected_apps.py           SHARED: prerequisite/connection state
│   ├── connected_apps.json         demo fixture (starts disconnected)
│   ├── feature_requests.py         Discovery's "log as a feature
│   │                               request?" — in-memory, deduped log
│   ├── analytics.py                in-memory analytics event log
│   ├── salesforce_mock.py          mock Salesforce API
│   ├── salesforce_schema.py        Track B's Salesforce object/field
│   │                               vocabulary — derived from app_catalog.py
│   ├── salesforce_fixture.json     contacts/accounts/account_team/...
│   ├── clickup_mock.py             second real app's mock service
│   │
│   ├── mailbox_lookup.py           capability 7: real testable
│   │                               conversations, scoped by inbox +
│   │                               optional contact-matching
│   ├── copilot.py                  outer turn loop: router -> (automation
│   │                               | apps) -> render; the app-action-
│   │                               required scope gate lives here
│   ├── docent.py                   capability-question answers, composed
│   │                               only from the schema files above
│   ├── workspace.py / workspace.json  entity-resolution fixture
│   ├── preview.py                  dry-run a final rule over the mailbox
│   │                               fixture
│   │
│   ├── serve_apps.py               Apps-panel dev server (port 8011) —
│   │                               the only active local entry point
│   ├── cli.py                      eval CLI (stdin -> stdout)
│   ├── make_mailbox.py / mailbox.json  demo inbox fixture
│   │
│   ├── test_*.py                   pure-code test suites, one per
│   │                               capability/concern (see engine/README.md
│   │                               for what each one locks in)
│   └── README.md                   dev changelog, every phase in order
│
├── eval/                        App Activation eval sets
│   ├── connector-eval-set.jsonl    6 records, Track B connector automations
│   ├── apps-eval-set.jsonl         12 records, Track A capabilities +
│   │                               the router boundary
│   ├── grader.py / report.py / run_eval.py  the connector set's harness
│   │                               (shared with the general engine
│   │                               originally, canonicalize/diff logic
│   │                               is schema-driven either way)
│   ├── apps_grader.py / apps_report.py  Track A's own small parallel
│   │                               harness (no trigger/actions to diff)
│   └── README.md                   what each set covers, how to run them
│
├── ui/                           Next.js playground
│   ├── app/apps/page.tsx           the Apps panel — the whole active UI
│   ├── app/page.tsx                "/" just redirects to "/apps"
│   ├── components/                 RuleCard, FeatureCard, QuestionForm,
│   │                               CapabilityBadges — all shared between
│   │                               what little "/" still does and "/apps"
│   ├── lib/api.ts                  the Apps panel's API client
│   ├── api/*.py                    Vercel serverless functions for the
│   │                               general panel — still deployed, but
│   │                               nothing in the active UI calls them
│   │                               anymore (see "Known gaps" below)
│   └── api/_engine/                a vendored copy of engine/ for Vercel
│                                   deployment — re-synced via
│                                   scripts/sync-engine.sh, never hand-edited
│
├── PRD.md                        product PRD — capability catalogue,
│                                 guardrails, open questions
├── README.md                     this file
└── legacy/                       everything from the pre-App-Activation
                                  scope — see legacy/README.md
```

## Run it

Needs Python 3.9+, an OpenAI API key, and `pip install openai`.

```bash
export OPENAI_API_KEY=sk-...        # engine/router.py also reads a sibling .env if present

# Apps panel — the only active local entry point
cd engine && python serve_apps.py   # -> http://127.0.0.1:8011
cd ui && pnpm dev                   # -> http://localhost:3000 (redirects "/" to "/apps")

# tests (no API calls — pure code, one file per capability/concern)
cd engine
python test_validator.py        python test_connector.py
python test_connector_planner.py python test_track_a.py
python test_native_action.py     python test_mapping_explanation.py
python test_real_conversation.py python test_feature_request_offer.py
python test_app_scope.py

# eval harness self-checks (no API calls)
cd eval && python grader.py --self-test && python apps_grader.py --self-test
python run_eval.py --engine echo               # connector-eval-set.jsonl, report must say 100%
python run_eval.py --engine echo --eval-set apps-eval-set.jsonl

# a real eval run needs OPENAI_API_KEY:
python run_eval.py --engine command --cmd "python ../engine/cli.py --apps-workspace"
python report.py runs/<run>.jsonl --failures
```

Re-vendor the engine into `ui/api/_engine` (needed after any `engine/`
change, before deploying) with `cd ui && bash scripts/sync-engine.sh`.

## Known gaps

- **`ui/api/*.py` (the Vercel serverless functions) still serve the
  general Automations panel's endpoints** (`/api/chat`, `/api/workspace`,
  `/api/vocabulary`, `/api/preview`), but nothing in the active UI calls
  them anymore now that "/" just redirects to "/apps". They're harmless
  (unreachable dead code from the deployed site's own frontend), not
  wired up incorrectly — but the Apps panel has no Vercel-deployed
  backend of its own yet (`serve_apps.py` is local-dev-only), so the
  deployed site currently has no working app-scoped API at all. Building
  that is real follow-on work, not done as part of this scoping pass.
- Real production activation, live (non-mock) API clients, real OAuth,
  and a multi-tenant account model are all explicitly out of scope — see
  `PRD.md` §9 for the full list and why.

## Data & privacy

- No real production data lives in this repo. `connected_apps.json`,
  `workspace.json`, `salesforce_fixture.json`, and `mailbox.json` are all
  demo fixtures.
- `eval/connector-eval-set.jsonl` and `eval/apps-eval-set.jsonl` are
  hand-authored records against those same fixtures — no real tenant data.

## Design decisions worth knowing

1. **The model only extracts, the code decides**: capability answers,
   badges, and gating are composed in code from the schema files, never
   invented by the model.
2. **Provenance over politeness**: the validator rejects any free-text
   value that doesn't appear in the user's own messages — scrubbed and
   re-asked, never guessed.
3. **Three connector mechanisms, in trust order**: a hand-vetted `recipe`
   (fastest, ships once per proven use case), a pre-built `native_action_id`
   (Hiver's own action block for the app), and a model-composed
   `custom_plan` (the least benefit of the doubt — must actually execute
   successfully against the mock before it counts as complete).
4. **Assumptions are disclosed, not asked**: a legal-either-way slot (like
   "run on everything") gets a stated assumption on the draft, confirmed
   at apply time — never a blocking question for something that already
   has a legal default.
5. **App Activation only, everywhere**: the same "does this touch a real
   app?" boundary is enforced once, in `copilot.py`, rather than
   re-implemented per surface — see this README's Charter section above.
