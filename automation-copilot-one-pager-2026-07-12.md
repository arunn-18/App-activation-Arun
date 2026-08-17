# One-pager: Automation Copilot

**Date:** 2026-07-12
**Author:** Mithil Verma
**Status:** Learning project, v2 rebuild in progress; not on the product roadmap
**Scope anchor:** v2 narrow scope (plain English to validated automation rule, conversation-type triggers only)

**Inputs synthesized:**
- [v1 prototype](../automation-copilot/README.md) (guardrails, knowledge base, golden dataset, eval harness, chat UI)
- [Last v1 eval run](../automation-copilot/testing/eval-runs/eval-20260701-000506.md) (2026-07-01)
- [v1 feedback log](../automation-copilot/feedback/feedback.jsonl)
- [v2 rule menu](rule-menu.md), verified against live builder screenshots (2026-07-07) and the [Automation Parity Confluence doc](https://hiverhq.atlassian.net/wiki/spaces/PRODUCT/pages/1434484746)
- [Competitor study: AI-assisted automation rule building](competitor-study-ai-automation-building-2026-07-12.md) (2026-07-12)

---

## TL;DR

Automation Copilot turns a plain-English request ("get invoice emails to the finance team") into a valid Hiver automation rule (trigger, conditions, actions). v1 (June 2026) proved the idea with prompt engineering alone: 30 of 36 held-out queries passed an LLM-judged eval. It also proved the ceiling: output was prose, so nothing guaranteed a generated rule was actually buildable, and every failure was a policy miss (built when it should have clarified, or vice versa), not a knowledge miss. v2 (restarted 2026-07-03) rebuilds around a **structured JSON rule spec plus a deterministic validator**, scoped to conversation-type triggers. The rule vocabulary is now verified from the live builder; the next milestone is the schema and validator with no LLM in the loop.

The competitive picture moved while this was a side project: **Zendesk shipped Admin Copilot to GA in May 2026** (NL creation of triggers, automations, and SLA policies, included at Suite Professional) and HubSpot ships Breeze workflow generation at Professional. No shared-inbox player has it. This stays a learning project, but the gap it prototypes against is now real and named.

---

## 1. Problem

**The product problem it prototypes against:** admins think in outcomes; the builder demands rule grammar. Hiver's automation builder spans 10 triggers, 18 condition fields with operator sets that differ per field (From Email supports five operators, To Email two), 11 actions, and a trigger-by-condition compatibility matrix that is documented nowhere admins can see. A copilot collapses that grammar into a sentence.

**The project's actual goals** (in priority order):
1. Learn how to build an AI assistant end to end: grounding, guardrails, structured output, evals, feedback loops.
2. Make it genuinely good at a narrow set of Hiver automation tasks, not plausibly good at everything.

---

## 2. What v1 was (June 2026)

| Piece | Implementation |
|---|---|
| Approach | Prompt engineering: system prompt assembled from `guardrails.md` (behavior) + `automation-knowledge.md` (vocabulary) + few-shot examples |
| Model | OpenAI gpt-4o, temperature 0.2 |
| Yardstick | 43-record golden dataset (7 held out as few-shot, 36 evaluated); categories include happy path, routing, multi-condition, needs-clarification, plan-gated, out-of-scope, escalation |
| Eval | Held-out queries scored by an LLM judge; graded markdown reports per run |
| Feedback loop | Browser chat UI with a flag-for-review button appending to `feedback.jsonl`; flags triaged to knowledge / guardrails / new golden rows |

**Final eval (2026-07-01): 30 pass, 4 partial, 2 fail of 36.**

---

## 3. What v1 taught

1. **Failures were policy misses, not knowledge misses.** gd-013 produced a finished rule when it should have offered AI-vs-keyword options; gd-002 asked a clarifying question when the request already implied a sender-domain match. The knowledge base was almost never the problem; the decision of when to build, clarify, or decline was.
2. **Prose output cannot be validated.** Correctness rested entirely on the LLM behaving, and the LLM judge grading prose is itself fuzzy. A structured spec allows exact-match scoring for rules and reserves judgment calls for behavior cases only.
3. **Grounding must come from the live builder.** The v1 knowledge base was scraped from docs and pricing pages and carried `⚠️ verify` flags throughout; the canonical help article couldn't even be scraped. v2's rule menu is built from builder screenshots instead.
4. **The compatibility matrix belongs in code.** Prompt instructions about which conditions pair with which triggers leak under paraphrase; a validator does not.

---

## 4. v2 architecture and scope

- **Structured JSON rule spec + deterministic validator.** The compatibility matrix and plan gating live as code, not prompt text. The assistant cannot emit an invalid rule; at worst it emits a wrong-but-valid one, which the eval catches by exact match.
- **Build order:** (1) schema + validator, no LLM; (2) single-turn extraction with structured output; (3) eval harness (exact JSON match for rules, LLM judge only for behavior cases); (4) multi-turn clarification; (5) thin UI + feedback. No frameworks, no RAG.
- **Scope:** conversation-type triggers only (Milestone-1 parity scope), one shared inbox. [rule-menu.md](rule-menu.md) is the single source of truth: 10 triggers, 18 condition fields with per-field operators, 11 actions, and the compatibility matrix, verified from 2026-07-07 builder screenshots plus the Automation Parity doc.

---

## 5. Current state (2026-07-12)

**Done:** rule menu draft v2; v1 kept intact as reference material.

**Open before coding starts:**
- The 10 verification gaps in rule-menu.md §6, chiefly: the T4 (moved to Shared Inbox) trigger is fully undocumented, the action dropdown's completeness is unconfirmed, `matches` operator semantics, the AND/OR group reading, and plan gating.
- Collect 20 to 30 real user phrasings from FR boards and tickets so the golden set stops being self-authored.
- Write the build-vs-clarify-vs-decline policy doc. This is the spec for the exact failure class that sank v1's eval cases.

---

## 6. Competitive landscape

Full study with sources and search logs: [competitor-study-ai-automation-building-2026-07-12.md](competitor-study-ai-automation-building-2026-07-12.md).

| Competitor | Has it? | Summary |
|---|---|---|
| Zendesk | **Yes** | Admin Copilot, GA May 2026: NL create/edit of triggers, automations, SLA policies; included at Suite Professional ($115/agent/mo); AI-generated trigger recommendations need the $50/agent Copilot add-on ($165 all-in) |
| HubSpot | **Yes** | Breeze generates complete workflows (triggers + actions) from a prompt; Professional ($90/seat/mo); generated workflows ship disabled by default |
| Front | Partial | "Build with AI" generates dynamic-variable logic and macro trees (Apr 2026), not full rules; Enterprise-gated ($105/seat) |
| Intercom | Partial | Fin Procedures drafted from NL (Feb 2026); Fin Operator (early access, May 2026) will build workflows from a prompt |
| Missive | Partial | AI runs *inside* manually built rules (prompt conditions/actions, BYOK, Mar 2025) |
| Freshdesk | No | Freddy Copilot is agent-facing only; "Conversational Actions" announced Feb 2024, never documented. Fast-follow risk: the $29 SKU and plumbing exist |
| Help Scout | No | Workflows fully manual; AI appears only as a draft-generation action |
| Gorgias | No | AI investment goes to the AI Agent layer (Guidance, Skills); rule builder untouched |

**What the study says back to this project:**
- The feature went from absent to two GA implementations inside 2026, and both price it as a mid-tier adoption driver, not an Enterprise carrot.
- Zendesk is the primary displacement target of Hiver's migration GTM; Admin Copilot now strengthens exactly the admin-simplicity story Hiver sells against them.
- No shared-inbox player ships full plain-English-to-rule. The segment Hiver actually competes in is open.
- Every shipped implementation is propose-and-approve with a hard-constrained scope. v2's validated-subset design matches the industry pattern, and a validator that *cannot* emit an invalid rule is a stronger claim than either GA implementation makes.

---

## 7. Packaging (deliberately open)

Not a decision this project needs yet; recorded so the thinking survives. Two live options if this productizes:

| Option | Shape | Competitor anchor | Trade-off |
|---|---|---|---|
| A. Adoption layer | Bundled wherever rule-based automations start (Growth+) | Zendesk includes base Admin Copilot at Professional; HubSpot includes Breeze at Professional | No direct revenue, but copilot conversations naturally surface Pro-gated capabilities (AI actions, advanced conditions), creating in-context upgrade moments. Growth admins struggle most with the builder |
| B. AI premium | Pro+, alongside AI Copilot and AI Agents | Consistent with Hiver's existing AI gating | Cleaner packaging story; risks gating the ease-of-use layer away from the segment that needs it, and concedes the "AI admin without enterprise pricing" wedge |

Elite-only is ruled out by the data: only Front gates its (partial) version at the top tier, and no one else followed.

**What would settle it:** automation adoption by plan (share of Growth vs Pro accounts with at least one active rule), and whether copilot sessions surface plan-gated features often enough to work as an upgrade channel.

---

## 8. Path to production (if ever promoted from learning project)

- Close the rule-menu verification gaps; 100% of the enum surface confirmed from the live builder, none from docs.
- The policy doc becomes the behavioral spec, with an eval bar before any EA: exact-match pass on golden rules, zero invalid rules emitted, no regression on clarify/decline/plan-gate cases.
- Propose-and-approve UX inside the admin panel builder; generated rules off by default (HubSpot's posture). A rule can send replies and call external APIs, so a generated rule is a privileged artifact: prompt-injection and abuse review required.
- Port off the personal OpenAI setup onto Hiver's AI infrastructure; add telemetry on accept / edit / abandon per generated rule.

---

## 9. Success measures

**Learning project (now):**
- Validator rejects 100% of a hand-built set of invalid specs (wrong trigger-condition pairs, empty values, gated features).
- Exact-JSON-match pass rate on the golden set at or above v1's judged 30/36, with the stricter metric.
- Policy cases (clarify / decline / plan-gate) pass without regression; this is the v1 failure class and the real test of v2.
- The feedback loop demonstrably turns flags into golden rows that then guard against regression.

**Product metrics (definitions only; targets deliberately unset, same convention as the shift-management one-pager):**

| Metric | Definition |
|---|---|
| Copilot share | % of new automations created via copilot vs the manual builder |
| Time to first automation | Days from account creation to first active rule, copilot cohort vs baseline |
| Generation quality | Edit distance between generated rule and the rule actually applied |
| Session completion | % of copilot sessions ending in an applied rule vs abandoned |
