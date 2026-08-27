# One-pager: Automation Copilot

**Date:** 2026-08-09
**Author:** Mithil Verma
**Status:** Prototype complete and measured; proposed for pilot evaluation. Supersedes the [2026-07-12 one-pager](automation-copilot-one-pager-2026-07-12.md), which described the v2 rebuild before it existed.

**Inputs synthesized:**
- [v2 engine + eval system](README.md) (schema/validator architecture, 4 eval suites, run history)
- [Production coverage analysis](eval/coverage-2026-08-09.md) (2026-08-09, full 90-day organic pool)
- [Competitor study: AI-assisted automation rule building](competitor-study-ai-automation-building-2026-07-12.md) (2026-07-12)
- [Entity-resolution live transcript](eval/runs/entity-smoke-2026-08-09.md)

---

## TL;DR

Automation Copilot turns a plain-English request ("get invoice emails to the finance team") into a valid Hiver automation rule through a short clarifying conversation. What was a learning project in July is now a working, measured prototype:

- **Scope:** rule-based (non-AI) automations. AI-based automation building is a separate team's project; in production the two merge, and this project's job is to be the best at the non-AI surface. (The engine does contain working AI-step support, kept as a built-but-gated extension for that merge — see §3.)
- It can fully build **92.2% of the 3,710 non-AI automations real Hiver admins created in the last 90 days** (3,422 rules, verified rule-by-rule against the production dump).
- Accuracy on that surface: **37/40 strict match** on real-world single-turn asks (judge-adjusted ceiling ~39/40), **14/14** on scripted multi-turn conversations (avg ~2 copilot turns, zero over-asking), **10/10** on workspace entity resolution ("assign to john" with two Johns asks; unknown tags get a create-first note).
- By construction it **cannot emit an invalid rule** and **cannot invent a tag, person, or inbox**: legality and provenance are enforced by a deterministic validator, not by prompt instructions.

Zendesk shipped Admin Copilot to GA in May; HubSpot ships Breeze workflow generation at Professional. No shared-inbox player has this. **The ask:** a design review, two engineering confirmations (below), and a decision on whether this graduates to a pilot.

---

## 1. Problem

Admins think in outcomes; the builder demands rule grammar. Hiver's automation builder spans 10 triggers, 18 condition fields with operator sets that differ per field, 11 actions, and a trigger-by-condition compatibility matrix documented nowhere admins can see. A copilot collapses that grammar into a sentence plus one or two clarifying questions.

---

## 2. What exists

One idea organizes the architecture: **the model only extracts; the code decides.**

| Layer | What it does | Guarantee it provides |
|---|---|---|
| Schema (code) | The legal vocabulary: 7 triggers, 16 condition properties with per-property operators, AI-extraction variables, 10 actions. Derived from the production database, so "valid" means "buildable in prod" | No off-vocabulary rule can exist |
| Extraction (LLM) | Maps the conversation onto a partial rule spec via strict structured output; may call workspace lookup tools (find user / list tags / list inboxes) | The only LLM in the loop; it never judges completeness or plans questions |
| Validator (code) | Legality, completeness, question planning, and provenance: every free-text value must appear in the user's own words, and every workspace lookup the model makes is re-verified in code from those words | No invented values; ambiguity is asked about, never guessed (two Johns get a pick-one question) |
| Rendering (code) | Draft with explicit holes, up to 3 planned questions per turn, final WHEN/IF/THEN plus machine JSON | The user always sees exactly what the system believes |

The clarification loop works from vague openings ("we get a lot of emails meant for jade, can you route them to her?") and converges in ~2 turns. Every user-facing surface renders the builder's own vocabulary ("New conversation (inbound or outbound) is created", not internal ids), so admins can verify rules in the language they already know.

---

## 3. Evidence

**Accuracy** (all runs reproducible; every run file carries model + prompt hash):

| Suite | What it tests | Result |
|---|---|---|
| Real-world core (40 records) | Single-turn asks mined from production, actual admin-built rule as ground truth | 37/40 strict (93%); the 3 misses are one genuinely ambiguous phrasing and two operator equivalences a judge would likely accept |
| Multi-turn (14 conversations) | Vague openings, drip-fed values, corrections, ambiguity, conversation closing | 14/14, avg ~2 copilot turns, 0 redundant questions |
| Entity resolution (10 records) | Fuzzy names, two-Johns ambiguity, unknown tags, invention bait; graded on the rule AND the conversation conduct | 10/10 |
| AI extraction (gated — outside pilot scope) | AI-step rules: detection variables, gates, note templates. Built and measured for the eventual merge with the AI-automation project | 12/16 strict at its best run; kept as an engine capability, not part of this pilot |

The eval methodology is the credibility anchor: eval sets are mined from 6,412 real production automations (90-day window, 1,088 tenants), stratified across the real usage distribution, with the actual admin-built rule as ground truth. This is not a demo scored on hand-picked examples.

**Coverage** ([full analysis](eval/coverage-2026-08-09.md)): the pilot surface builds **92.2% of the non-AI pool** (3,422 of 3,710 organic automations; AI-step automations, 4.7% of the total, belong to the sister project). The unlock curve for the rest, ranked by measured demand:

| Add | Coverage of non-AI pool |
|---|---|
| Current pilot surface | 92.2% |
| + saved-list operators (`is_present_in`: "sender is in our VIP list") | ~95% |
| + custom fields | ~97% |
| Everything further (incl. connectors, at under 1%) | tail |

Notable: connectors, despite roadmap gravity, block almost nothing. The demand-ranked pilot scope is current surface + saved-list operators + custom fields.

---

## 4. Competitive position

Full study with sources: [competitor study](competitor-study-ai-automation-building-2026-07-12.md). Zendesk Admin Copilot GA'd May 2026 (included at Suite Professional); HubSpot Breeze generates workflows at Professional; Front/Intercom partial; Freshdesk, Help Scout, Gorgias absent. Two things matter:

1. **No shared-inbox player ships plain-English-to-rule.** The segment Hiver competes in is open, and Zendesk (Hiver's primary migration displacement target) now strengthens exactly the admin-simplicity story Hiver sells against them.
2. Every shipped implementation is propose-and-approve over a constrained scope. A validator that provably cannot emit an invalid rule is a **stronger claim than either GA implementation makes**, and we can demonstrate it.

---

## 5. Packaging (unchanged, deliberately open)

Two live options if this productizes: bundle where automations start (Growth+, the Zendesk/HubSpot pattern; copilot conversations naturally surface Pro-gated capabilities as upgrade moments) or gate at Pro+ alongside the existing AI SKUs. Elite-only is ruled out by the competitive data. What would settle it: automation adoption by plan, and how often copilot sessions touch plan-gated features. Details in the July one-pager, section 7.

---

## 6. What a pilot decision needs

**From engineering (cheap confirmations, they de-risk everything):**
1. Confirm condition-group semantics (groups AND'd, conditions within a group OR'd). Inferred from data and flagged everywhere it matters; one conversation settles it.
2. Confirm internal API equivalents of the three lookup tools (list tags, find user, list inboxes) exist with an admin session. The prototype's fixture-backed tools were designed as the spec for these.
3. Longer-term: serve the rule vocabulary itself (triggers, fields, operators, actions, plan gates) from the backend per tenant, the way the prototype now serves builder-vocabulary labels — a hardcoded schema can drift from the builder; an API cannot.

**From design:** a review of the propose-and-approve UX. The prototype's chat contract (draft with explicit holes, at most 3 questions per turn, final rule requiring explicit apply) is a working starting point; generated rules should ship disabled by default (HubSpot's posture).

**From security (before any EA):** a generated rule is a privileged artifact (it can send replies and, later, call external APIs), so prompt-injection and abuse review of the extraction path.

**Engineering-shape notes:** the LLM surface is one extraction call per conversation turn (avg 2.2 turns per rule) plus bounded tool calls; everything else is deterministic code, which is what makes the accuracy reproducible and the behavior auditable. Exact token cost per rule is not yet profiled; it is the next measurement if this proceeds. Porting means swapping the personal OpenAI setup for Hiver's AI infrastructure and adding accept/edit/abandon telemetry.

---

## 7. Success measures (product; definitions only, targets unset)

| Metric | Definition |
|---|---|
| Copilot share | % of new automations created via copilot vs the manual builder |
| Time to first automation | Days from account creation to first active rule, copilot cohort vs baseline |
| Generation quality | Edit distance between generated rule and the rule actually applied |
| Session completion | % of copilot sessions ending in an applied rule vs abandoned |

The July one-pager's learning-project success measures are all met: the validator rejects invalid specs by construction, exact-match accuracy exceeds v1's judged score under a stricter metric, the v1 failure class (build-vs-clarify policy) is now code, and the eval loop demonstrably turns failures into regression guards (five documented iteration ladders in the [engine README](engine/README.md)).
