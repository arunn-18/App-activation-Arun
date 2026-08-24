# PRD — Apps Activation: an app-agnostic capability engine

**Status:** Implemented (v2.14) · **Owner:** Arun Nayak · **Last updated:** 2026-08-24
**Related:** [PR #1](https://github.com/arunn-18/App-activation-Arun/pull/1) · `engine/README.md` (dev changelog)

---

## 1. Problem

Hiver's copilot can already turn a chat request into a working automation for **one** app (Salesforce), through **one** hand-built connector recipe. Every additional app or use case today means new schema, new prompts, new validation code, and new tests written by hand — there is no shared foundation that lets a new Marketplace app plug in with configuration alone.

At the same time, admins setting up an app capability get no explanation of *why* the copilot is proposing a given setup, no way to see it work against a real conversation before trusting it, and no consistent distinction between "this is a pre-built app action," "this is a general API automation," and "this isn't possible."

## 2. Goals

1. **Onboard a new Marketplace app with configuration, not code.** Adding an app's auth, object/field model, capability catalogue, and API-documentation path should be enough to bring it into every existing conversational flow — no new prompts, validators, or UI branches per app.
2. **Cover six capabilities generically**, each expressed as one config shape any app can populate:
   - Auth (connect / prerequisite state)
   - Record-level configuration (which objects an admin exposes)
   - Field-level configuration — view usecases
   - Field-level configuration — write usecases (e.g. create a Contact from Hiver)
   - App-native automation (a pre-built action block, e.g. "create a ClickUp task" — not an API call the engine composes)
   - API-driven automation (no native action exists, so the engine composes an API call chain itself)
3. **A consistent 7-step conversational flow** for any capability:
   1. Identify the usecase from the chat
   2. Map it to the existing catalogue of usecases/capabilities
   3. **Explain** the mapping back to the user (why this capability solves their workflow)
   4. Decide the bucket — Track A (existing app capability), Track B (API automation), or **not possible**
   5. Walk the user through setup, unblocking them at each question
   6. **Never change the steps of an existing app capability** while generalizing the framework under it
   7. Offer to test the finished capability against a real conversation
4. **Guardrails commensurate with capability.** Every new mechanism (a native action, a model-composed API plan) earns trust through the same discipline the first recipe had — prerequisite gating, provenance on free-text values, and no execution without validation — not less scrutiny just because it's newer or more automatic.

## 3. Non-goals

- Building a real (non-mock) API client for any app. Auth, versioning, and pagination against a live org are called out explicitly as follow-on work per app (see §9).
- A generic no-code "connect any REST API" builder. The engine still needs each app's real object/field catalogue and, for API automations, a description of which endpoints are safe to call — it removes duplicate hand-authored schema, not the need to describe the app at all.
- Changing what counts as "complete" for an existing Track A feature. Guardrail #6 above is a hard constraint, not a suggestion.

## 4. Users

- **Admin setting up a capability** — the primary conversational user of the copilot described here.
- **App owner adding a new Marketplace app** to this engine — configures §7 below once per app.
- **Agent/end-customer** — indirectly affected: sees the resulting automation or app feature run in a real conversation.

## 5. The capability catalogue

| # | Capability | Track | Mechanism |
|---|---|---|---|
| 1 | Auth | shared | `connected_apps.json` + `connected_apps.py` (prerequisite/connection state, pinned `api_version`) |
| 2 | Record-level configuration | A | `apps/setup.py` step 2 — pick objects from `app_catalog.objects_for()` |
| 3 | Field config — view usecase | A | `apps/setup.py` step 3 — pick fields from `app_catalog.field_catalog()` |
| 4 | Field config — write usecase | A | same step, sourced from `app_catalog.writable_field_catalog()`; `FEATURES[...]["kind"] == "write"` — proven on TWO apps (`salesforce_create_contact`, `clickup_create_task_from_hiver`) |
| 5 | App-native automation | B | `automation/schema.py: NATIVE_ACTIONS` — a pre-built Hiver action block, not a composed call |
| 6 | API-driven automation | B | `automation/schema.py: RECIPES` (hand-vetted) or a model-composed `custom_plan` (validated by `plan_validator.py`) |

A request that fits none of these — no matching `FEATURES` entry, no `NATIVE_ACTIONS`, no valid `custom_plan`, no `RECIPES` match — is escalated honestly as `unsupported_requests`, never forced into the nearest available bucket.

### Three connector mechanisms, in trust order

1. **`recipe`** — a hand-vetted, fully-tested chain. The fast path; ships once per proven use case.
2. **`native_action_id`** — a pre-built Hiver action block for the app (e.g. ClickUp's task-creation block). Not an API call the engine composes — the distinction is stated back to the user in the mapping explanation (§8).
3. **`custom_plan`** — a chain the model composes at runtime from the app's object/field catalogue when neither of the above matches but the ask fits the same *shape* (a lookup, then an assign/tag terminal). Gets the least benefit of the doubt: every reference must resolve against the real catalogue, values must chain from something already extracted (never a forward reference), and the plan must actually **execute successfully** against the mock before it counts toward `status: complete`.

## 6. The 7-step flow, mapped to code

| Step | Behavior | Where |
|---|---|---|
| 1. Identify usecase | Router's first-call classification (`automation` vs `app_setup`), then each track's own extraction schema | `router.py`, `automation/extract.py`, `apps/extract.py` |
| 2. Map to catalogue | Extraction resolves the ask to a `FEATURES` entry, a `RECIPES`/`NATIVE_ACTIONS` id, or a composed plan | same |
| 3. Explain the mapping | One sentence, composed only from existing schema/registry data, shown once per conversation | `copilot._mapping_explanation()`, gated by `is_first_turn` |
| 4. Decide the bucket | Track A / Track B / neither — `unsupported_requests` when nothing fits | `automation/extract.py` rule 19, `apps/extract.py` rule 20 |
| 4b. Discovery: no match → feature request | A genuinely novel ask (`unmappable`, not an already-categorized `unsupported_requests` gap) is offered as a "log this as a feature request?" courtesy — explicit, admin-confirmed, never automatic | `copilot._apply_feature_request_offer()`, `feature_requests.py`, `analytics.py` |
| 5. Guided setup | One blocking question at a time; same `QuestionForm` UI component for every track | `automation/validator.py`, `apps/setup.py` |
| 6. No regressions to existing steps | Enforced by keeping every pre-existing test assertion unchanged while adding new, additive test files per capability | `test_track_a.py`, `test_connector.py` (unchanged), new suites below |
| 7. Test on a real conversation | Real mailbox conversations (not placeholder emails) offered as the test target, for both tracks | `mailbox_lookup.py`, `apps/setup.preview_feature()`, the `test_contact_email` choice-question |

## 7. Onboarding a new app — the config surface

Adding an app requires touching exactly these, and nothing in the shared engine code:

1. **`app_catalog.py`** — one `CATALOG[app]` entry: its objects, and each field's `label`/`type`/`view`/`write`/`custom`/`assignable`/`taggable` flags. This alone drives both tracks' field pickers, the planner's vocabulary, and the guardrails' notion of "a real field."
2. **`connected_apps.json`** — the app's auth/prerequisite entry, including its pinned `api_version` (see §9).
3. **A mock (or real) service module** — `query()`/lookup ops the executor can call, registered in `automation/executor.py`'s service registry.
4. **Capability-specific registration, only for what the app actually offers:**
   - Track A features it supports → `apps/schema.py: FEATURES`
   - A native action block, if the app has one → `automation/schema.py: NATIVE_ACTIONS`
   - A hand-vetted recipe, if a use case deserves the fast path → `automation/schema.py: RECIPES`

No changes to `router.py`, either `extract.py`, `validator.py`, `plan_validator.py`, or any UI component are required to bring in a new app's objects/fields or native actions. **Proof, not just claim:** ClickUp was onboarded this way — a fixture, a mock module, and a registry entry, zero edits to shared mechanism code.

## 8. Guardrails

- **Per-field flags are deliberate claims, never inferred from type.** A string field is not automatically viewable, writable, assignable, or taggable — every flag defaults to `False`.
- **Provenance**: any free-text value an action uses (a test email, a `target_name`) must appear verbatim in the user's own words — never invented by the model.
- **Prerequisite gating** applies uniformly — a native action or a composed plan is blocked on the same "is this app connected" check a recipe already had, no exceptions for new mechanism types.
- **A composed plan gets a stricter completeness bar than a recipe.** A recipe already proved correct once (via its own test suite) can complete on a clean `no_match`. A plan that has never run before must actually execute successfully against the mock to count as complete.
- **Track A's existing steps are frozen.** Generalizing the field catalog or adding the write-usecase branch must never change the 4-step order, question wording, or completeness rule for an existing feature — verified by re-running every pre-existing assertion unchanged.
- **API version pinning.** A real integration's auth is issued against one API version; every call for that connection must target that same version's endpoints, never "latest" or an inferred version. `connected_apps.api_version()` is the one place this is read from — see §9.
- **Every automation names its enable scope.** A top-level `enabled_inboxes` slot is required the moment a real workspace is loaded, the Track B analogue of Track A's own "which shared inbox(es)" step — never left implicit or workspace-wide by default.
- **A prerequisite gate must offer its own fix, not just name itself.** Any mechanism (recipe, native action, composed plan) that blocks on an unmet prerequisite must offer the real one-click fix when one exists (`connected_apps.PREREQUISITE_ACTIONS`) — a static "must be connected" message with nothing to click is a dead end, not a guardrail.
- **A gate with no one-click fix must still be self-serve.** `connected_apps.PREREQUISITE_REMEDIATION`/`remediation_for()` — when the block can't be flipped by Hiver (e.g. Salesforce's Account Team/CSM setup), the error names the exact steps to clear it, never just the flag that's blocking it. `None` when no remediation text is on file yet — an honest gap, never an invented instruction.
- **Feature-request logging is explicit, never silent.** `unmappable` asks (a genuinely novel gap — not an already-categorized `unsupported_requests` one) get a real "log this as a feature request?" yes/no question; logging only ever happens after the admin says yes. Stubbed locally (`feature_requests.py`, `analytics.py`) — no real ClickUp/Jira/Amplitude destination exists in this repo, same "mock it, never fake it" discipline as `connected_apps.json`.

## 9. Explicitly out of scope for this phase (flagged, not silently dropped)

- **Live (non-mock) API clients per app** — auth flow, real endpoint calls, pagination, rate limits. The planner/guardrail layer is app-agnostic (it operates on the abstract `{object, field, where}` shape), but each app still needs its own real client before a composed plan or native action can run against production data.
- **API documentation ingestion** — today, "showing the path for API documentation" is a manual step for whoever configures `app_catalog.py`; there is no automated discovery of an app's schema from its public API docs.
- **Real OAuth / credential storage** — `connected_apps.json` remains a mock fixture of connection state.
- **Known error-code diagnostics for a test-run failure.** Checked before building: every mock create op (`salesforce_mock.create_contact`, `clickup_mock.create_task`) "always succeeds" — there is no real API integration to fail with a real error code yet, so a `known_errors` lookup would have to invent codes that don't correspond to anything real. Blocked on the live API clients above existing first.
- **Real Amplitude/ClickUp-Jira wiring.** `analytics.py`/`feature_requests.py` are local, in-memory stubs with the exact shape a real integration would need (event name + properties; app/request/why/track) — swapping either for a real destination means replacing one function's body, not any caller.
- **Making live-validation (capability 7's test-run) a blocking gate.** Stays a courtesy shown alongside completion, per Guardrail "Track A's existing steps are frozen" above — a deliberate decision, not an oversight, revisited only as its own isolated change if ever.
- **Real production activation.** "Enabled"/"complete" in this engine records intent only — `ui/components/FeatureCard.tsx` says so explicitly ("demo: recorded here, not actually toggled in Hiver"). Needs a real Hiver backend connection this repo doesn't have.
- **Team rollout** (checklists, in-app agent nudges once a capability activates) and **a multi-tenant "UG"/account model** — both need a real agent-facing product surface and real account/workspace identity this single-fixture prototype doesn't have.
- **Onboarding a third app (e.g. Asana).** Deliberately sequenced after closing gaps on the two existing apps (Salesforce, ClickUp) first, so a new app doesn't inherit gaps already known and fixed.

## 10. Testing & success criteria

All new capabilities ship with a pure-code, no-LLM test suite (routing/extraction from a live model is out of scope for this sandbox; everything downstream of "the model produced this classification" is verified):

| Suite | Coverage | Result |
|---|---|---|
| `test_validator.py` | automation schema/validator core, incl. `enabled_inboxes` | 56/56 core + 62/62 units |
| `test_connector.py` | recipe-based connector, incl. `connect_requested` | 29/29 |
| `test_connector_planner.py` | dynamic-plan guardrails | 18/18 |
| `test_track_a.py` | full app-setup flow incl. write usecase | 45/45 |
| `test_native_action.py` | native-action mechanism (ClickUp), 6-field form, app-scoped vocab | 24/24 |
| `test_mapping_explanation.py` | step-3 explanation, all mechanisms | 7/7 |
| `test_real_conversation.py` | step-7 real-conversation testing, incl. ClickUp write feature | 23/23 |
| `test_feature_request_offer.py` | Discovery's feature-request offer, self-serve remediation, example-phrasing wiring | 21/21 |

No regression to any pre-existing assertion across the whole body of work. UI (`ui/lib/api.ts`, `RuleCard.tsx`, `FeatureCard.tsx`) kept in lockstep, `npx tsc --noEmit` clean.

Also a golden eval set, `eval/apps-eval-set.jsonl` (12 records, graded by a small parallel harness — `apps_grader.py`/`apps_report.py`) — the first eval coverage for Track A ("Apps" panel) capabilities and the router boundary between Track A/B, not just Track B automations. See `eval/README.md`'s own "Apps set" section.

## 11. Open questions

- What does "minimal config" look like for an app whose API needs OAuth scopes beyond a single connect toggle?
- Should `plan_validator.py`'s guardrails (assignable/taggable field flags, `MAX_PLAN_STEPS`) be configurable per app, or is one global policy right for every Marketplace app?
- How should API-documentation references actually be attached per app — a URL field in `app_catalog.py`, or a separate registry?
- Where should a real feature request actually land (ClickUp board? Jira? a PM inbox?) once this repo has real credentials to wire `feature_requests.py` up to — needs a named destination and access before that follow-on task can start.
- Should the feature-request offer also apply to `unsupported_requests` (already-categorized gaps like custom fields/approval flows), or stay scoped to `unmappable` only as it is today? Left narrow deliberately (§8) to avoid logging noise for gaps Hiver already knows about, but worth revisiting once real usage data exists.
- Instrumentation is intentionally partial: only `apps_activation_feature_request_logged` is wired (`analytics.py`'s `EVENTS` class names all six the source PRD specifies). Wiring `flow_started`/`capability_mapped`/`setup_step_completed`/`test_run`/`activated` touches many more call sites across both tracks and needs its own scoped pass.

---

## 12. Architecture reference

```
engine/
├── router.py                    # 1st call each turn: classifies track (automation | app_setup)
│                                   before either package's schema loads
│
├── app_catalog.py                # THE single per-app object/field catalog: one entry per
│                                   app/object/field (view/write/custom/assignable/taggable flags).
│                                   Both packages below DERIVE their schemas from this — onboarding
│                                   a new app's objects/fields means editing only this file.
│
├── automation/                  # Track B: per-conversation rules (trigger → conditions → actions),
│   │                             including connector recipes AND dynamic connector plans
│   ├── __init__.py
│   ├── schema.py                 # triggers, conditions, actions, RECIPES, NATIVE_ACTIONS
│   │                                (capability 5, e.g. ClickUp task creation), UNSUPPORTED
│   ├── extract.py                 # 2nd LLM call — fills automation-only wire schema; routes to
│   │                                recipe | native_action_id | custom_plan | unsupported
│   ├── planner.py                 # read-only schema-exploration tool calls (list_objects,
│   │                                describe_object) feeding a model-composed custom_plan
│   ├── plan_validator.py          # guardrails for a model-composed plan: real object/field
│   │                                refs only, no forward references, assignable/taggable-only
│   │                                terminals, MAX_PLAN_STEPS, no benefit of the doubt vs. RECIPES
│   ├── validator.py               # pure code: provenance, entity resolution, question planning —
│   │                                4-way connector branch (recipe / native / plan / neither)
│   └── executor.py                # runs a recipe's chain, a validated plan's chain, OR a native
│                                     action for real (against mocks) — run_chain() / run_native_action()
│
├── apps/                        # Track A: configuring an existing app feature (no trigger/actions)
│   ├── __init__.py
│   ├── schema.py                  # FEATURES (with "kind": "view"|"write" — capability 4),
│   │                                 FIELD_CATALOG/WRITABLE_FIELD_CATALOG derived from app_catalog.py
│   ├── extract.py                  # 2nd LLM call — fills app-setup-only wire schema
│   └── setup.py                    # pure code: resolve_setup() — auth → objects → fields → inboxes;
│                                      preview_feature() (capability 7, real-data test preview)
│
├── connected_apps.py             # SHARED: prerequisite/connection state + api_version() pin
│                                    (both tracks read it; covers salesforce AND clickup);
│                                    PREREQUISITE_REMEDIATION/remediation_for() — self-serve
│                                    fix-it text for a gate with no one-click PREREQUISITE_ACTIONS
├── connected_apps.json           # demo fixture (starts disconnected; per-app api_version)
├── feature_requests.py            # Discovery's "log this as a feature request?" -- in-memory,
│                                     deduped-by-(app,request) log; no real ClickUp/Jira destination yet
├── analytics.py                   # in-memory analytics event log; EVENTS names all 6 Amplitude
│                                     events the Apps Activation PRD specifies, only 1 wired so far
├── salesforce_mock.py            # SHARED: mock Salesforce API — query()/describe_object()/
│                                    list_objects() primitives + describe_fields()/describe_writable_fields()
├── salesforce_schema.py          # Track B's object/field vocabulary — DERIVED from app_catalog.py
├── salesforce_fixture.json       # contacts/accounts/account_team/opportunities/cases
│
├── clickup_mock.py                # second real app's mock service (create_task), proving
│                                     "onboard with config, not code"
│
├── mailbox_lookup.py              # capability 7: cross-references mailbox.json against an
│                                     app's fixture contacts to offer REAL testable conversations
│
├── copilot.py                     # outer turn loop: router → (automation | apps) → render;
│                                     _mapping_explanation() (step 3, first-turn-only);
│                                     _render_feature_preview()/_test_conversation_suggestions()
├── docent.py                      # capability-question answers — describes all 3 connector
│                                     mechanisms (recipe / native action / composed plan)
├── workspace.py / workspace.json  # entity-resolution fixture (tags/agents/inboxes)
├── preview.py                     # dry-run a final rule JSON over the mailbox fixture
│
├── serve2.py                      # Automations-panel dev server (port 8001)
├── serve_api.py                   # structured JSON API for the UI (port 8010)
├── serve_apps.py                  # Apps-panel dev server — also returns native_actions per app
├── cli.py                         # eval CLI (stdin → stdout)
├── simulate.py                    # multi-turn self-play simulation harness
├── make_mailbox.py / mailbox.json # demo inbox fixture
│
├── test_validator.py              # automation schema/validator suite — 56/56 core, 62/62 units
├── test_connector.py              # connector recipe suite — 29/29
├── test_connector_planner.py      # dynamic-plan guardrail suite — 18/18
├── test_track_a.py                # app-setup flow suite — 45/45 (write-usecase branch, 2 apps)
├── test_native_action.py          # ClickUp native-action suite — 24/24 (6 fields, one-block form)
├── test_mapping_explanation.py    # step-3 explanation suite — 7/7
├── test_real_conversation.py      # capability 7 suite — 23/23 (2 apps' write features)
├── test_feature_request_offer.py  # Discovery/remediation/example-phrasing suite — 21/21
└── README.md                      # dev changelog (through the v2.14 Discovery-offer entry)
```

---

## Reference

<!-- add your reference material below -->
