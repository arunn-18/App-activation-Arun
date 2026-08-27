# Competitor study: AI-assisted automation rule building

**Feature scope (as understood):** an admin uses AI or natural language to create, edit, or get suggestions for workflow automation rules (trigger, conditions, actions) in a helpdesk product. Not in scope: AI agents that answer tickets, AI reply drafting, AI triage/classification. Adjacent capabilities are covered only where they blur into rule building.
**Date:** 2026-07-12
**Competitors covered:** Freshdesk, Zendesk, Front, Help Scout, Gorgias, HubSpot Service Hub, Intercom, Missive (plus a Hiver baseline column)

## At-a-glance comparison

| Competitor | Has it? | What it's called | Lowest tier | Add-on? | Last meaningful update | Source |
|---|---|---|---|---|---|---|
| **Hiver (baseline)** | No | n/a. Closest: Automations Center template library (Mar 2026); AI Tasks visual builder is AI *in* workflows, not AI *building* rules | n/a | n/a | Mar 2026 (templates, non-AI) | [changelog](https://updates.hiverhq.com/changelog) |
| Zendesk | **Yes** | Admin Copilot | Suite Professional, $115/agent/mo annual (included at GA) | Copilot add-on $50/agent/mo for AI-generated trigger/autoreply recommendations | GA May 2026 | [help](https://support.zendesk.com/hc/en-us/articles/10013995711386-About-admin-copilot) |
| HubSpot Service Hub | **Yes** | Breeze Assistant ("Create workflow → With AI") | Professional, $90/seat/mo annual | None (Breeze included; heavy use consumes HubSpot Credits, extra at $0.010/credit) | May 2026 (KB update) | [KB](https://knowledge.hubspot.com/workflows/use-ai-assistants-in-workflows) |
| Front | Partial | "Build with AI" (dynamic variables in Smart Rules; full macro trees) | Macros with AI: Professional $65/seat/mo; rule-side (dynamic variables + Smart Rules): Enterprise $105/seat/mo | Autopilot (AI rule templates) from $0.05/conversation | Apr 2026 | [help](https://help.front.com/en/articles/2282) |
| Intercom | Partial | Fin Procedures "Draft with AI"; Fin Operator (early access) | Fin on all plans at $0.99/outcome; deterministic Workflows builder needs Advanced $85/seat/mo | Fin Operator: waitlist, no public pricing | May 2026 (Operator EA) | [help](https://www.intercom.com/help/en/articles/12495167-fin-procedures-explained) |
| Missive | Partial | AI Rules (AI executes *inside* manually built rules) | Productive, $24/user/mo annual | None; BYOK (OpenAI/Anthropic/Gemini billed to your key) | Mar 2025 | [docs](https://missiveapp.com/docs/advanced-features/rules/ai-rules) |
| Freshdesk | No | n/a (Freddy AI Copilot is agent-facing only) | n/a | Freddy AI Copilot $29/agent/mo exists, but no rule building in it | Jun 2026 (overview article still lists no rule AI) | [help](https://support.freshdesk.com/support/solutions/articles/50000010359-overview-of-freddy-ai-for-ticketing) |
| Help Scout | No | n/a (Workflows are manual; AI Draft exists only as a workflow *action*) | n/a | n/a | Jun 2026 (SLA workflow triggers, manual) | [updates](https://updates.helpscout.com/) |
| Gorgias | No | n/a (Managed Rules are pre-built templates, not AI-generated) | n/a | n/a | Feb 2025 (Skills, AI-agent side) | [updates](https://updates.gorgias.com/) |

**Headline:** two GA implementations exist (Zendesk, HubSpot), both shipped or matured in 2026, both included at the mid tier rather than sold as an Enterprise carrot. Among Gmail-native / shared-inbox players (Front, Help Scout, Missive, Gorgias), nobody ships full plain-English-to-rule generation.

---

## Per-competitor deep dive

### Zendesk
**Status:** Yes
**Product name:** Admin Copilot (conversational assistance + AI recommendations), building on intelligent triage.

**How it works:**
- Conversational assistant available from any Admin Center page; admins ask it in natural language to "create or edit business rules like triggers, macros, and automations"; all changes are previewed and approved before applying ([EAP announcement](https://support.zendesk.com/hc/en-us/articles/10434881963802-Introducing-Admin-Copilot-your-AI-powered-admin-assistant-Open-EAP)).
- Scope per help doc: "Create, update, or delete triggers, automations, SLA policies, and more", plus troubleshooting and setup Q&A. On by default; only account owners can toggle access ([About admin copilot](https://support.zendesk.com/hc/en-us/articles/10013995711386-About-admin-copilot)).
- AI recommendations engine (7 types): flags unused triggers/automations/macros, suggests macro content, and generates trigger/autoreply recommendations from intelligent-triage classifications (intent, sentiment, language, entities). Admin clicks "Review trigger" and lands on the create-trigger page with conditions and actions prefilled ([AI recommendations](https://support.zendesk.com/hc/en-us/articles/9598690362010-Reviewing-and-implementing-AI-recommendations-to-automate-tasks)).
- Recommendations run on a weekly monitoring cadence, not real time (same source).

**Packaging & pricing:**
- Included "at no additional cost" for Suite Professional ($115/agent/mo annual) and above since GA ([What's new June 2026](https://support.zendesk.com/hc/en-us/articles/10831960298522-What-s-new-in-Zendesk-June-2026); [pricing](https://www.zendesk.com/pricing/)).
- The richer recommendation types (task-automation triggers/autoreplies, auto-assist config) require the Copilot add-on, $50/agent/mo annual ([pricing](https://www.zendesk.com/pricing/)).
- Not available on Suite Team ($55). Enterprise pricing is contact-sales.

**Recency:** Open EAP Mar 17, 2026; GA May 26, 2026 for Suite Professional+ ([source](https://support.zendesk.com/hc/en-us/articles/10434881963802-Introducing-Admin-Copilot-your-AI-powered-admin-assistant-Open-EAP)). Intelligent-triage settings opened to Professional+ from Jul 1, 2026.

**Notable gaps / limits:** docs don't enumerate which object types the assistant *cannot* modify; ~6 weeks past GA, maturity unproven; recommendation engine gated behind the $50 add-on.

### HubSpot Service Hub
**Status:** Yes (most mature implementation found)
**Product name:** Breeze Assistant workflow generation ("Create workflow → With AI").

**How it works:**
- Generates a complete workflow from a natural-language prompt, including enrollment triggers and actions; HubSpot recommends the "When [this happens], then [do this]" prompt structure ([KB article](https://knowledge.hubspot.com/workflows/use-ai-assistants-in-workflows)).
- In-editor "Build with AI" panel adds or edits actions via prompt; proposed actions are previewed highlighted in blue and iteratively refined before saving (same source).
- Guardrails: in-editor Breeze can suggest enrollment triggers but cannot modify existing triggers; cannot add go-to-workflow, delay-until-event, format-data, branching, webhooks, A/B test emails, or Salesforce/Google-integration actions; AI-generated workflows are **off by default** pending human review (same source).
- Data Hub Pro/Enterprise: Breeze may auto-generate custom code actions when no standard action fits (same source).
- Requires two admin toggles (generative AI access + Breeze Assistant access).

**Packaging & pricing:**
- Follows the workflows tool: Professional ($90/seat/mo annual) or Enterprise ($150/seat/mo) on any hub ([tiers](https://knowledge.hubspot.com/workflows/use-ai-assistants-in-workflows); [prices](https://www.hubspot.com/pricing/service)).
- Breeze Assistant itself is included with all products and plans; heavier Breeze features consume HubSpot Credits: 500 (Starter) / 3,000 (Pro) / 5,000 (Enterprise) included, extra at $0.010/credit ([Understand Breeze](https://knowledge.hubspot.com/ai/understand-breeze)).

**Recency:** KB article last updated May 14, 2026; lineage traces to INBOUND Sep 2023 AI Assistants for workflows (then only AI-written workflow descriptions, Pro+ private beta) ([release notes](https://community.hubspot.com/t5/Releases-and-Updates/INBOUND-2023-Release-Notes/ba-p/845546)).

**Notable gaps / limits:** long exclusion list (no branches, webhooks, format-data via AI); can't touch triggers when editing an existing workflow; Starter customers get nothing.

### Front
**Status:** Partial (AI builds rule *components* from natural language; the rule shell stays manual)
**Product name:** "Build with AI" (inside rule and macro editors), living in Smart Rules; Autopilot-powered rule templates in the Rule Library.

**How it works:**
- In the dynamic-variable panel of linear rules, branching rules, and macros, admins click "Build with AI" and describe the variable in natural language; the variable's steps auto-generate, with keep / undo / re-prompt refinement ([dynamic variables](https://help.front.com/en/articles/2282); [Smart Rules how-to](https://help.front.com/en/articles/2201)).
- For macros, AI generates the full decision tree from a plain-language description; for rules, AI builds only the dynamic-variable logic inside the rule, while trigger/filters/actions are configured manually ([product update](https://community.front.com/product-updates)).
- Stated limits: no third-party integration actions via AI; no prompt history ([source](https://help.front.com/en/articles/2282)).
- Adjacent (AI *inside* a rule): Rule Library ships Autopilot-powered templates ("Tag with Autopilot", "Move with Autopilot", "Reply with Autopilot Instructions") that use AI's answer to a question as the rule condition; marked as requiring a paid add-on ([rule library](https://help.front.com/en/articles/2114)).

**Search log (for the "no full-rule generation" verdict):** `site:help.front.com AI rule OR "natural language" OR copilot OR "create rule with AI" OR "smart rules"` surfaced articles 2201, 2283, 2282, 2114, 2109; `site:community.front.com "build macros and dynamic variables with AI"` surfaced the Apr 2026 update. None describe generating a complete rule from a prompt.

**Packaging & pricing:**
- Macros-with-AI: Professional ($65/seat/mo annual, up to 50 seats). Dynamic-variables-with-AI and Smart Rules: Enterprise only ($105/seat/mo annual listed) ([pricing](https://front.com/pricing); [Smart Rules](https://help.front.com/en/articles/2283)).
- Rule quotas by tier: Starter ($25, ≤10 seats) 10 rules; Professional 20; Enterprise unlimited + Smart Rules.
- Add-ons: Autopilot from $0.05/conversation; Copilot $20/seat/mo; Smart QA $20; Smart CSAT $10 ([pricing](https://front.com/pricing)).

**Recency:** "Easily build macros and dynamic variables with AI" shipped Apr 3, 2026 ([product updates](https://community.front.com/product-updates)).

**Notable gaps / limits:** the genuinely NL-buildable piece is Enterprise-gated; no full-rule generation; no third-party actions via AI.

### Intercom
**Status:** Partial (no AI drafting in the deterministic Workflows builder; two fast-moving adjacent capabilities)
**Product name:** Fin Procedures ("Draft with AI"); Fin Operator (early access).

**How it works:**
- The deterministic Workflows builder is a visual drag-and-drop canvas with no documented AI-assisted creation ([Procedures vs Tasks vs Workflows](https://www.intercom.com/help/en/articles/14077835-procedures-vs-tasks-vs-workflows)).
- Fin Procedures: multi-step automations combining natural-language instructions with deterministic controls. "Share an outline of your process" and Fin drafts a Procedure you refine ([Procedures explained](https://www.intercom.com/help/en/articles/12495167-fin-procedures-explained), updated May 2026). Feb 2026 update added AI drafting from natural language, sub-procedures, and AI-suggested test simulations ([blog](https://www.intercom.com/blog/procedures-simulations-updates/)). Procedures are executed by the Fin AI agent on customer intent, not fired deterministically, and cannot be called from a Workflow step.
- Fin Operator (closest to true AI rule building): a conversational ops agent that builds Procedures from a single prompt (triggers, multi-step instructions, edge cases, simulation test), with the same claimed for Guidance rules, data connectors, monitors, and workflows ([Operator blog](https://www.intercom.com/blog/introducing-operator/), May 2026). Proposal-based: admin approves, edits, or rejects; Operator never publishes or modifies directly ([Operator explained](https://www.intercom.com/help/en/articles/14707198-fin-operator-explained)). Early access via waitlist.

**Search log (for the "no NL creation in Workflows canvas" verdict):** `site:intercom.com/changes workflow "AI" generate OR build OR describe` returned only AI call summaries, IVR workflows, visual bot builder; no changelog entry for AI-generated workflows in the builder.

**Packaging & pricing:**
- Procedures ride on Fin: all plans, $0.99 per outcome. Seats: Essential $29 / Advanced $85 / Expert $132 per seat/mo annual. The deterministic Workflows builder requires Advanced ([plans explained](https://www.intercom.com/help/en/articles/9061614-intercom-plans-explained); [pricing](https://www.intercom.com/pricing)).
- Fin Operator: early access, no public pricing (a positioning signal in itself).

**Recency:** Procedures AI-drafting expansion Feb 2026; Fin Operator early access May 2026.

**Notable gaps / limits:** Operator's "builds workflows" claim is blog-level and early-access; AI-built automations carry a $0.99 per-execution cost, unlike free deterministic rules.

### Missive
**Status:** Partial (AI executes inside rules; AI does not build the rule)
**Product name:** AI Rules.

**How it works:**
- Admins build the rule manually; AI is available as a **prompt condition** (admin writes a plain-language instruction such as "Is this customer angry? Respond ONLY YES or NO"; the AI's answer gates the rule) and as AI **actions** (add AI note, create draft with AI, add tasks with AI, add labels with AI) ([AI Rules docs](https://missiveapp.com/docs/advanced-features/rules/ai-rules); [launch blog](https://missiveapp.com/blog/autopilot-for-your-inbox-ai-rules-have-arrived)).
- BYOK model: connect OpenAI, Anthropic, or Gemini; model choice per rule (Fast = synchronous, Powerful = async); AI usage billed to your provider account, Missive charges nothing extra (docs above).
- Nothing generates a rule from a description; the natural language lives in the prompt evaluated at runtime.

**Search log:** `site:help.missiveapp.com rules AI ...` returned zero results (docs live at missiveapp.com/docs, not the help subdomain); domain-restricted searches on missiveapp.com surfaced only the AI Rules docs and launch blog. No result suggests AI-generated rules.

**Packaging & pricing:** AI Rules require Productive ($24/user/mo annual) or Business ($36); Starter ($14) excludes them ([pricing](https://missiveapp.com/pricing)). No add-on fees; BYOK.

**Recency:** AI Rules shipped Mar 13, 2025 ([blog](https://missiveapp.com/blog/autopilot-for-your-inbox-ai-rules-have-arrived)); providers since expanded to Anthropic and Gemini (docs current Jul 2026).

**Notable gaps / limits:** no AI-assisted rule creation at all; BYOK setup friction for non-technical admins.

### Freshdesk (Freshworks)
**Status:** No (nothing shipped in Freshdesk; one adjacent capability announced in marketing but never documented)
**Product name:** n/a. Closest: Freddy AI Copilot (agent-facing) and announced "Conversational Actions".

**How it works (closest adjacencies):**
- The Freddy AI overview (last modified Jun 2026) enumerates every Copilot feature: writing assistant, summarize, reply suggester, solution article generator, sentiment, auto triage, agent assist bot, thank-you detector, live translate. None involve creating or editing automation rules ([overview](https://support.freshdesk.com/support/solutions/articles/50000010359-overview-of-freddy-ai-for-ticketing)).
- Auto Triage uses AI to prepopulate ticket fields from historical patterns: classification, not rule authoring ([source](https://support.freshdesk.com/support/solutions/articles/50000002117-setting-up-auto-triage)).
- "Conversational Actions" was announced in the Freddy Copilot GA blog (Feb 2024): admin tasks like setting up SLAs, adding agents, changing business hours via natural language. Even as announced it covers admin config objects, not automation rules, and no help-center article documents it as shipped ([blog](https://www.freshworks.com/theworks/company-news/freddy-copilot-customer-service/)).
- What shipped for rule-building UX is non-AI: curated automation templates, Oct 2024 ([new features](https://www.freshworks.com/freshdesk/new-features/)).
- Caveat: sibling product Freshservice (ITSM) markets Freddy Copilot updating workflows via natural language; do not confuse with Freshdesk ([source](https://www.freshworks.com/it-service/solutions/ai-copilot/)).

**Search log (negative-finding evidence):** `site:support.freshdesk.com "describe your automation" OR "generate rule" OR "AI automation builder" OR "create automation with AI" OR "natural language rule"` returned no results. `site:support.freshdesk.com "conversational actions" ...` returned only Freddy Self-service chatbot articles. `site:support.freshdesk.com "Freddy" automation OR "natural language" OR copilot OR "create rule"` returned only agent-facing features. Community search likewise.

**Packaging & pricing (context):** base plans Growth $19 / Pro $55 / Enterprise $89 per agent/mo annual ([pricing](https://www.freshworks.com/freshdesk/pricing/)). Freddy AI Copilot add-on $29/agent/mo (announced Feb 2024; price no longer shown on the live pricing page). Freddy AI Agent $49 per 100 sessions ([manage add-ons](https://support.freshdesk.com/support/solutions/articles/50000011515-manage-freddy-ai-add-ons)).

**Recency:** Freddy Copilot GA Feb 2024; overview article last modified Jun 2026 still lists no rule-building AI.

**Notable gaps / limits:** credible fast-follow risk: the Copilot plumbing and $29 SKU already exist, and "Conversational Actions" is announced-but-undocumented.

### Help Scout
**Status:** No
**Product name:** n/a. Workflows have no AI-assisted creation; the AI portfolio (AI Drafts, AI Assist, AI Summarize, AI Answers, AI Agents) is agent- or customer-facing.

**How it works (closest adjacency):**
- Workflows are classic if-then rules built manually ([Get started with Workflows](https://docs.helpscout.com/article/22-get-started-with-workflows); [Automatic Workflows](https://docs.helpscout.com/article/1399-automatic-workflows)).
- Only AI touchpoint is AI as an *action*: a "Generate an AI Draft" workflow action; the workflow itself is hand-built ([AI Drafts](https://docs.helpscout.com/article/1570-ai-drafts)).

**Search log (negative-finding evidence):** `site:docs.helpscout.com workflow AI OR "natural language" OR "AI assist" OR "generate workflow"` returned AI Drafts, Automatic Workflows, AI Assist, AI Answers, AI Agents; none describe AI-assisted workflow creation. Two further domain-restricted queries on "plain English" / "workflow suggestions" returned nothing. Fetched https://updates.helpscout.com/ directly: Mar-Jun 2026 entries cover SLA workflow triggers (Jun 17, 2026), availability, views; no AI workflow builder.

**Packaging & pricing (context):** Workflows included from Standard ($25/user/mo monthly, ~16% off annual); higher limits on Plus ($45) and Pro ($75). AI Assist/Drafts/Summarize included Standard+; AI Answers add-on $0.75/resolution ([pricing](https://www.helpscout.com/pricing/)).

**Recency:** latest workflow change is SLA-triggered workflows, Jun 2026 ([updates](https://updates.helpscout.com/)); still manual creation.

### Gorgias
**Status:** No (AI investment is entirely in the AI Agent layer; the deterministic rule builder is untouched)
**Product name:** n/a. Adjacent: AI Agent "Guidance" and "Skills" (plain-English configuration of the AI agent, not rule generation).

**How it works (closest adjacencies):**
- Rules remain manual if/when/then builders; closest to assisted creation is the Rule Library with "Managed Rules": pre-built templates you install, "no code and no setup", template-based rather than AI-generated ([updates](https://updates.gorgias.com/publications/managed-rules-are-coming-to-your-local-rule-library)).
- Guidance: custom natural-language instructions for the AI Agent, with Actions insertable inline ([docs](https://docs.gorgias.com/en-US/create-guidance-to-give-ai-agent-custom-instructions-1362592)). Skills (Feb 2025): WHEN/IF/THEN instruction sets tied to customer intents, steering AI Agent behavior ([updates](https://updates.gorgias.com/)). Both are admin-authored plain English steering an LLM agent; the AI does not generate a deterministic rule object.

**Search log (negative-finding evidence):** `site:docs.gorgias.com rules create AI generate OR suggest OR "natural language"` returned Guidance and AI Agent explainers only. `site:updates.gorgias.com rules OR "rule" AI create suggest` returned CSAT-in-rules, Instagram conditions, metafields, Managed Rules; no AI rule creation. Fetched https://updates.gorgias.com/ directly: no such entry in the feed.

**Packaging & pricing (context):** helpdesk priced by ticket volume, not per agent (Starter/Basic/Pro/Advanced/Enterprise). **Pricing is no longer public**: the pricing page shows no dollar amounts; exact per-ticket and per-automated-interaction rates are only visible in-account ([pricing](https://www.gorgias.com/pricing); [billing docs](https://docs.gorgias.com/en-US/how-youre-billed-for-using-gorgias-199385)). AI Agent is pay-per-resolution on every plan.

**Recency:** updates feed current through Helpdesk 2.0 (Dec 2024) and Skills (Feb 2025); as of Jul 2026 no AI-assisted rule creation.

---

## Synthesis

**Common patterns across competitors:**
- Only two GA implementations of NL rule building exist (Zendesk Admin Copilot, GA May 2026; HubSpot Breeze workflow generation, matured through May 2026). Both are propose-and-approve: the admin always previews, and HubSpot goes further by shipping every AI-generated workflow disabled by default.
- Nobody sells this as an Enterprise carrot except Front. Zendesk includes the base copilot at Suite Professional; HubSpot includes Breeze at Professional. Monetization sits in adjacent add-ons (Zendesk's $50 Copilot for the recommendation engine, Front's per-conversation Autopilot), not in the rule-building assistant itself. The feature is priced as an adoption driver.
- Every shipped implementation constrains scope hard: HubSpot maintains a long exclusion list (no branching, webhooks, trigger edits), Front excludes third-party actions, Zendesk doesn't document its object coverage. Shipping a validated subset is the industry pattern, which matches the v2 conversation-triggers-only cut.
- The market is converging from two directions: deterministic-rule vendors bolt NL creation onto the builder (Zendesk, HubSpot, Front), while AI-agent-first vendors (Intercom, Gorgias) make the agent configurable in plain English and leave the rule builder alone. Intercom's Fin Operator (early access, May 2026) suggests "prompt to workflow" goes GA there within quarters.

**Differentiation opportunities for Hiver:**
- In the shared-inbox / Gmail-native segment (Front, Help Scout, Missive, Gorgias), no one ships full plain-English-to-rule generation. Front's version is Enterprise-gated at $105/seat and only generates rule components. A mid-tier full-rule builder would be first in this segment.
- Zendesk is the displacement target of Hiver's migration GTM, and Admin Copilot now directly strengthens Zendesk's admin-simplicity story. An unanswered gap here erodes "Hiver is easier to run" as a migration argument.
- A deterministic validator (compatibility matrix and plan gating as code) is a defensible quality claim: Zendesk and HubSpot still rely on the human preview step to catch invalid logic; a copilot that cannot emit an invalid rule is a stronger promise.

**Table-stakes Hiver shouldn't ship without:**
- Propose-and-approve flow; never auto-apply, and consider HubSpot's off-by-default posture for generated rules.
- Honest handling of unsupported and plan-gated requests (already a v1 golden-dataset category); every shipped competitor constrains scope explicitly rather than hallucinating capability.
