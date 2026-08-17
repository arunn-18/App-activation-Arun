# Automation Copilot — deferred to next version

Decided 2026-07-22, during the clarifying-question fix. These were scoped, discussed, and deliberately **not** built yet. They are the next structural step after the prompt-level fixes land.

## What shipped instead (v1 prototype, 2026-07-22)

The "scope ask-first" fix: when a user asks for actions on incoming email with **no conditions** and without saying *all/every* (e.g. "when a conversation comes in apply tag refund and assign it to john"), the copilot now asks whether the rule should fire on everything or a subset **before** drafting a rule, instead of defaulting to "(no conditions — applies to all)". Implemented purely at the prompt/dataset level: guardrails §2/§5, a SCOPE ASK-FIRST rule in the engine header, few-shot gd-044, and eval records gd-045–gd-047 (including two guards against over-asking).

## Deferred item 1 — entity validation (does the tag / assignee exist?)

> **Shipped 2026-08-09 (v2.5)** — implemented against the v2 engine rather than this
> v1-era plan: `engine/workspace.py` + fixture, tool-calling loop in `extract.py`,
> re-verification + entity checks in `validator.py`. One deliberate deviation: unique
> fuzzy matches resolve-and-disclose instead of asking (the v2 over-asking evidence
> post-dates this plan); ambiguous matches still always ask. See `engine/README.md`.

The engine is a single stateless Chat Completions call over two static markdown files. It cannot know whether a "refund" tag exists or which agents are named John. Plan, in order:

1. **Mock workspace fixture** — `knowledge/workspace.json`: tags, agents (full names + emails), shared inboxes, plan tier of a fictional workspace. Inject as a "WORKSPACE STATE" section in `build_system_prompt()`. Deterministic, so the eval stays reproducible.
2. **Entity-resolution guardrails** — exact match → use it; fuzzy match ("john" → "John Doe", or two Johns) → ask the user to pick, never silently choose; no match → say so and offer the rule with a "create this tag first" note. Plus golden records for each case.
3. **Tool-calling loop** — replace the single-shot `complete()` with a function-calling loop exposing `list_tags(inbox)`, `find_user(name)`, `list_inboxes()`. Prototype tools read `workspace.json`; production tools hit Hiver's internal APIs with the admin's session. This is the piece that scales past prompt-injection (real workspaces have hundreds of tags) and doubles as the spec for engineering.

Touches `engine.py` (loop), `serve.py` (inherits it), eval harness (must tolerate multi-step calls).
