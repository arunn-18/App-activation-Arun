# Automation Copilot — Playground UI

A test bench and demo surface for the [v2 copilot engine](../../Documents/Claude/product/projects/automation-copilot-v2/README.md):
plain English in the left pane, the rule assembling live in the right pane. Built to be
extended — the engine returns full machine state per turn, and every panel here is just
a rendering of it.

## Run it

Two processes:

```bash
# 1. the engine API (from the v2 repo)
cd ~/Documents/Claude/product/projects/automation-copilot-v2/engine
../../automation-copilot/.venv/bin/python serve_api.py     # -> http://127.0.0.1:8010

# 2. this UI
cd ~/sandbox/automation-copilot-ui
pnpm dev                                                    # -> http://localhost:3000
```

The header dot shows engine connectivity; click it to see the demo workspace
(tags, agents, shared inboxes) the entity resolver knows about.

## What to try

- A vague ask: "we get a lot of emails meant for jade, can you route them to her?"
  Watch the ledger's amber holes fill as you answer.
- "assign every new incoming email to john" — two Johns exist; the copilot must ask,
  never pick.
- "tag emails from acme.com appropriately" — no tag named; it asks instead of
  shopping the workspace tag list.
- After a rule completes, say "that's about it" — the copilot wraps up instead of
  repeating itself, and the ledger badge flips to "Final — ready to build".
- Apply a completed rule ("Create this rule" → confirm) — it lands in the **Rule log**
  (header) with an outcome: ACCEPTED (applied as generated), EDITED (adjusted after
  first completion, the generation-quality signal), or ABANDONED (completed but reset
  without applying). Stored in localStorage only; this prototypes the accept/edit/
  abandon telemetry from the one-pager. Applying is a demo action — nothing is built
  in Hiver.

Pilot scope is the non-AI surface (AI automation building is a separate team's
project). The engine still renders AI-step rules if you ask for one — that capability
is gated, not removed.

## Architecture

Built on shadcn/ui (radix-nova preset), Inter, and a monochrome + blue theme, laid
out like Amplitude's agent chat: sidebar (new automation + session history, persisted
in localStorage), centered conversation, results inline as cards. components.json is
configured, so `pnpm dlx shadcn add <x>` drops in primitives that already match.
Token note: custom colors live under non-shadcn names (`brand`, `bone`, `ink`,
`hairline`) because shadcn owns `accent`/`muted` — two collisions taught us that.

```
app/page.tsx                  shell: sidebar (sessions), centered chat, composer,
                              Sheet panels (workspace, rule log), streaming loop
components/RuleCard.tsx       inline per-turn rule card: WHEN/AI/IF/THEN from the
                              spec, dashed holes for open slots, resolutions as
                              margin notes, apply/confirm + machine JSON on the
                              latest card only
lib/sessions.ts               localStorage sessions (Today / 30 days / Older)
components/QuestionForm.tsx   quick-answer form (shadcn questionnaire) for the
                              validator's structured questions — choices for the
                              two-Johns pick, scope, status enums; submitting
                              composes a chat message, never a side channel
components/WorkingSteps.tsx   agent transparency: live checklist of REAL pipeline
                              events while a turn runs (extraction, each workspace
                              lookup, validation), collapsing to an intent-headed
                              summary per turn — no fake timers, every step is a
                              server-sent event from the engine
lib/api.ts                    typed client: plain + streaming (SSE) endpoints,
                              progress labels, assistant-bubble composer
lib/telemetry.ts              local accept/edited/abandoned rule log
```

The engine API (`serve_api.py`, `POST /api/chat`) returns `respond_structured()`:
status, the partial spec, planned questions, entity resolutions and notes, and the
final prod-shape rule when complete. Anything you want to build next — an apply
button, per-turn diffing, a rule library, accept/edit telemetry — starts from that
payload, not from parsing prose.

Override the API location with `NEXT_PUBLIC_COPILOT_API` if the engine runs elsewhere.
