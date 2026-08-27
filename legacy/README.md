# Legacy

**Archived 2026-08-27** as part of narrowing this engine's charter to **App
Activation only** — every automation it builds now has to touch a real app
via a connector action (see `engine/copilot.py`'s own scope gate and
`PRD.md`). This directory holds everything from the general
(non-app-connected) automation-copilot engagement that preceded App
Activation: still real, still historically accurate, just not what this
repo builds anymore. Nothing here is wired into the active build, tests, or
eval harness — see each subdirectory's own README/notes for what moved and
why, and what to adjust (mostly import/sys.path fixes) if any of it ever
needs to run again.

| Directory | What moved here | Active equivalent |
|---|---|---|
| `engine/` | `serve2.py`, `serve_api.py`, `simulate.py` — the general Automations panel's dev servers and self-play harness | `engine/serve_apps.py` |
| `eval/` | `real-world-eval-set.jsonl`, `multi-turn-eval-set.jsonl`, `entity-eval-set.jsonl`, `adversarial-eval-set.jsonl`, `coverage-2026-08-09.md`, `build/` (the real-world set's mining pipeline), `runs/` (139 historical run/report files) | `eval/connector-eval-set.jsonl`, `eval/apps-eval-set.jsonl` |
| `ui/` | `app/page.tsx` (the "/" route), `lib/sessions.ts`, `lib/telemetry.ts`, `lib/api-automations.ts` (the general panel's API client — `fetchWorkspace`/`fetchVocabulary`/`sendChat`/`sendChatStream`/etc.), `components/StreamedText.tsx`, `components/WorkingSteps.tsx` | `ui/app/apps/page.tsx` ("/" now redirects there) |
| `docs/` | Historical product-process docs (one-pagers, a competitor study, call-prep notes, a rule-menu spec, deferred-scope notes, a teardown walkthrough) | `PRD.md` (repo root) |

Every moved engine/Python file's own docstring notes what import or
`sys.path` change it needs to run from its new location — none of them
are runnable as-is from here, since their sibling modules (`copilot`,
`router`, `grader`, etc.) stayed in the active tree.
