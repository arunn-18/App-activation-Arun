# PRD — Apps Activation: an app-agnostic capability engine

**Status:** Implemented (v2.20) · **Owner:** Arun Nayak · **Last updated:** 2026-08-27
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
| 4 | Field config — write usecase | A | same step, sourced from `app_catalog.writable_field_catalog()`; `FEATURES[...]["kind"] == "write"` — proven on TWO apps (`salesforce_create_contact`, `clickup_create_task_from_hiver`). Two OPTIONAL follow-on steps, ClickUp only (v2.18): Prefill Fields (default values for the write form) and Quick Access (a recorded-only badge toggle) |
| 5 | App-native automation | B | `automation/schema.py: NATIVE_ACTIONS` — a pre-built Hiver action block, not a composed call. ClickUp's `clickup_create_task` (v2.18) asks the admin WHEN + WHAT TO LOOK FOR before ever rendering the card, instead of silently defaulting the trigger and assuming "runs on everything" |
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
| 4b. Discovery: no match → feature request | A genuinely novel ask (`unmappable`, not an already-categorized `unsupported_requests` gap) is offered as a "log this as a feature request?" courtesy — explicit, admin-confirmed, never automatic. Never offered on a bare capability question (already answered, nothing to build) | `copilot._apply_feature_request_offer()`, `feature_requests.py`, `analytics.py` |
| 4c. Capability questions get real badges | A capability question's answer carries structured, clickable `FEATURES`/`RECIPES`/`NATIVE_ACTIONS` entries alongside the prose — never a misleading "rule built" card for a question that built nothing. Both the badges AND the prose answer are scoped to whichever app was actually named (`docent._integration_answer()`), and neither the card nor a lingering "what should happen when this fires?" form can leak through, gated on `actions` being empty rather than `trigger` (which gets a rule-4 default fill even for a bare question) | `docent.relevant_capabilities()`, `docent._integration_answer()`, `CapabilityBadges.tsx` |
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
| `test_validator.py` | automation schema/validator core (SHARED mechanics — provenance, entity resolution, coherence — every app automation still needs), incl. `enabled_inboxes`, ClickUp's ask-before-showing scope override | 73/73 units |
| `test_connector.py` | recipe-based connector, incl. `connect_requested` | 29/29 |
| `test_connector_planner.py` | dynamic-plan guardrails | 18/18 |
| `test_track_a.py` | full app-setup flow incl. write usecase | 45/45 |
| `test_native_action.py` | native-action mechanism (ClickUp), 6-field form, app-scoped vocab, ask-before-showing scope block | 28/28 |
| `test_mapping_explanation.py` | step-3 explanation, all mechanisms, app-aware wording (not hardcoded to Salesforce) | 9/9 |
| `test_real_conversation.py` | step-7 real-conversation testing incl. ClickUp write feature, Prefill Fields/Quick Access (steps 5/6), mailbox-scoped + contact-match-optional `testable_conversations()` | 35/35 |
| `test_feature_request_offer.py` | Discovery's feature-request offer, self-serve remediation, example-phrasing wiring, capability-question suppression + app-scoped badges/prose, docent dedup/keyword fixes, wholly-unmappable question suppression | 36/36 |
| `test_app_scope.py` | the App Activation charter itself (v2.20) — an automation needs a real app action to be in scope | 12/12 |

No regression to any pre-existing assertion across the whole body of work (285 unit cases total across 9 suites). UI (`ui/lib/api.ts`, `RuleCard.tsx`, `FeatureCard.tsx`, `CapabilityBadges.tsx`) kept in lockstep, `npx tsc --noEmit` and `next build` clean. `test_validator.py`'s former "schema coverage" pass (against the general `real-world-eval-set.jsonl`) was removed, not just left stale — that eval set moved to `legacy/eval/` along with the rest of the pre-App-Activation material (see §10c).

Also a golden eval set, `eval/apps-eval-set.jsonl` (12 records, graded by a small parallel harness — `apps_grader.py`/`apps_report.py`) — the first eval coverage for Track A ("Apps" panel) capabilities and the router boundary between Track A/B, not just Track B automations. See `eval/README.md`'s own "Apps set" section.

## 10a. ClickUp UX-clarity pass (v2.18, 2026-08-26)

A live product review of ClickUp's two capabilities asked for five things
together, all shipped in this pass — see `engine/README.md`'s v2.18 entry
for the full writeup:

1. **Chip/badge naming** now states the track: "Create tasks automatically
   via automation" (Track B) vs. "Create task manually from conversations"
   (Track A) — previously both read as "create a ClickUp task."
2. **Description wording** dropped internal engineering jargon ("not an
   API call this engine composes"); a real bug was fixed along the way —
   the mapping explanation said "an existing Salesforce app capability"
   for *any* matched Track A feature, ClickUp's included.
3. **Ask-before-showing**, scoped to `clickup_create_task` only: the
   RuleCard no longer appears pre-filled with a silently-defaulted trigger
   and an assumed "runs on everything" scope — the admin is asked WHEN and
   WHAT TO LOOK FOR first, with a legal "every conversation" escape hatch.
4. **Prefill Fields + Quick Access** — two new optional setup steps for
   `clickup_create_task_from_hiver` (capability 4's write branch), never
   blocking completion, both skippable.
5. **Mailbox picker** ahead of the existing conversation picker in
   capability 7's write-test flow, scoped to the feature's own enabled
   inbox(es) — plus an app-aware fix so ClickUp's testable conversations
   aren't filtered by Salesforce contact matching, a concept ClickUp's
   write feature never had.

All five were scoped narrowly (ClickUp only, or the one feature/action
that needed it) rather than generalized speculatively — Salesforce's
existing capabilities are untouched by this pass.

## 10b. Docent's irrelevant/repeated answers and a trigger-vocabulary gap (v2.19, 2026-08-27)

A live conversation surfaced three problems: (1) a real keyword-matching
bug in `docent.py` — plain substring matching meant short keys matched
inside unrelated words ("ai" inside "explain", "tag" inside "advantage"),
producing genuinely irrelevant answers, not just unhelpfully generic ones
— fixed with leading-word-boundary matching; (2) the same generic answer
could render twice in a row (a bare "yes" misclassified as another
capability question) — fixed with a dedup check; (3) an ask needing a
trigger this engine has no vocabulary for at all (a third-party app's own
state change, e.g. "when the linked ClickUp task closes") was silently
built into a wrong partial rule instead of being named as impossible —
fixed with a new extraction rule, plus stripping the resulting bogus
WHEN/IF/THEN questions once nothing legal survives. Full writeup:
`engine/README.md`'s v2.19 entry.

## 10c. App Activation only: narrow the engine's whole charter (v2.20, 2026-08-27)

The ask: "clean the code and make it according to the App's usecase only
(including app automations)... not any automations without the app
actions." This directly hardens Goal 2 and the capability catalogue (§5)
above into an enforced boundary, not just a description of what's built:
`copilot.py` now rejects (status `invalid`, a clear message) any
automation-track turn with real content but zero connector actions among
its actions — Hiver itself can build a pure-tag/assign/status rule fine,
it's just no longer something THIS engine builds. Generic actions
(tag/assign/status/note/reply/notify/inbox-move) still combine freely
with a real app action in the same rule — the boundary is "does this rule
touch an app at all," not "is every action app-specific."

Everything from the engine's broader, pre-App-Activation scope — the
general Automations panel and its own eval sets (real-world/multi-turn/
entity/adversarial), historical product-process docs — moved to
`legacy/` rather than being deleted; see `legacy/README.md` for the full
map and `README.md` (repo root, rewritten from scratch in this pass) for
the current schema-first structure. Full writeup: `engine/README.md`'s
v2.20 entry.

## 11. Open questions

- What does "minimal config" look like for an app whose API needs OAuth scopes beyond a single connect toggle?
- Should `plan_validator.py`'s guardrails (assignable/taggable field flags, `MAX_PLAN_STEPS`) be configurable per app, or is one global policy right for every Marketplace app?
- How should API-documentation references actually be attached per app — a URL field in `app_catalog.py`, or a separate registry?
- Where should a real feature request actually land (ClickUp board? Jira? a PM inbox?) once this repo has real credentials to wire `feature_requests.py` up to — needs a named destination and access before that follow-on task can start.
- Should the feature-request offer also apply to `unsupported_requests` (already-categorized gaps like custom fields/approval flows), or stay scoped to `unmappable` only as it is today? Left narrow deliberately (§8) to avoid logging noise for gaps Hiver already knows about, but worth revisiting once real usage data exists.
- Instrumentation is intentionally partial: only `apps_activation_feature_request_logged` is wired (`analytics.py`'s `EVENTS` class names all six the source PRD specifies). Wiring `flow_started`/`capability_mapped`/`setup_step_completed`/`test_run`/`activated` touches many more call sites across both tracks and needs its own scoped pass.

---

## 12. Architecture reference

Moved to the repo root `README.md` (rewritten from scratch in v2.20) —
keeping one accurate tree instead of two that drift out of sync. That
file is schema-first: it points at `apps/schema.py`, `automation/
schema.py`, and `app_catalog.py` as the actual place to start reading,
then the full current directory structure (`engine/`, `eval/`, `ui/`,
`legacy/`), how to run everything, and the known gaps.

---

## Reference

<!-- add your reference material below -->
