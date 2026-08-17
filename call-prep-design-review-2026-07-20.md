# Call prep: Automation Copilot first design prototype

**Date:** 2026-07-20
**Attendees:** Nitesh (has partial context), Anurag M., Sudipta, Shankar (support), Akshay (support)

---

## 30-second intro (cold open)

> Automation Copilot turns a plain-English request, like "get invoice emails to the finance team", into a valid Hiver automation rule: trigger, conditions, actions. The problem it attacks: admins think in outcomes, but our builder demands rule grammar. 10 triggers, 18 condition fields where operators differ per field, 11 actions, and a trigger-condition compatibility matrix documented nowhere an admin can see. The copilot collapses all of that into a sentence. Today I want to walk you through the first design prototype.

## One level deeper (if asked "where is this at?")

- **v1 (June):** pure prompt engineering, proved the idea. 30 of 36 held-out queries passed an LLM-judged eval. Also proved the ceiling: prose output, so nothing guaranteed a rule was buildable, and every failure was a policy miss (built when it should have clarified, or the reverse).
- **v2 (rebuild, started early July):** structured JSON rule spec plus a deterministic validator. Compatibility matrix and plan gating live as code, so the assistant cannot emit an invalid rule. Scoped to conversation-type triggers, one shared inbox.
- **Status honesty:** started as a learning project; there is a Milestone 1 ClickUp ticket ("Supervisor AI: create automations using natural language") tracking it as a real initiative.

## Competitive one-liner (if credibility is questioned)

Zendesk shipped Admin Copilot to GA in May 2026 (NL creation of triggers, automations, SLA policies, included at Suite Professional). HubSpot Breeze generates full workflows at Professional. **No shared-inbox player (Front, Help Scout, Missive, Gorgias) has full plain-English-to-rule.** The segment we compete in is open, and Zendesk is the exact displacement target of our migration GTM.

Every shipped version is propose-and-approve with hard-scoped coverage. Our validated-subset design matches the pattern, and "cannot emit an invalid rule" is a stronger claim than either GA implementation makes.

## Why Shankar and Akshay are in the room

They see L1 automation tickets, which is exactly the evidence gap in the project:

1. **Real phrasings.** The golden dataset is still self-authored; the open task is collecting 20 to 30 real user phrasings. Ask them for the actual language customers use when asking for automation help.
2. **Confusion patterns.** Which parts of the builder generate the most tickets: trigger choice, condition operators, the AND/OR grouping, plan gating? This shapes the build-vs-clarify-vs-decline policy, the exact failure class that sank v1's eval.
3. **Failure tolerance.** They can pressure-test the propose-and-approve posture: what does a wrong-but-valid rule cost a customer, and what would they want the copilot to refuse to do?

Concrete asks to land before the call ends:
- A sample of L1 automation tickets (or a saved view) to mine for phrasings.
- Their top 3 "customers always get this wrong" builder concepts.

## Likely questions and answers

- **"Will it create wrong rules?"** It cannot create an *invalid* one; the validator blocks incompatible trigger-condition pairs and gated features. A wrong-but-valid rule is caught by propose-and-approve; generated rules should ship off by default (HubSpot's posture).
- **"What about plan-gated features?"** Gating lives in the validator as code. The copilot can also surface gated capabilities in context, which is the adoption/upsell angle (packaging deliberately open: Growth+ adoption layer vs Pro+ AI premium; Elite-only ruled out by competitor data).
- **"When does this ship?"** Not committed. Path to production requires: rule-menu enum surface 100% verified from the live builder, policy doc as behavioral spec with an eval bar, prompt-injection review (a rule can send replies), and porting off the personal OpenAI setup onto Hiver AI infra.

## Watch-out

The ClickUp Milestone 1 ticket (86d3m6jaq) description and Confluence page 2174615564 contain an unauthorized pitch written under your name on 2026-07-12 (fabricated personas P1-P4, use cases U1-U6, an "Option A recommended" packaging call you never made). If Nitesh's context comes from either surface, he may hold beliefs about the project you never asserted. Be ready to reset: the local one-pager is the only authorized framing, and packaging is deliberately open.
