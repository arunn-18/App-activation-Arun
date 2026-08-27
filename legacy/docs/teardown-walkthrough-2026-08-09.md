# Teardown: one request through the v2 copilot, end to end

**Date:** 2026-08-09
**Purpose:** a learning walkthrough of the v2 pipeline, traced with real artifacts from a live run. Everything below (specs, validator verdicts, grader diffs) was produced today by actually running the code, not written by hand.

The record under the microscope is **rw-020** from the real-world eval set. It came from production automation `137031`: a real admin built this rule, and the eval set pairs it with a plain-English ask:

> "Anything addressed to or CC'd to jade@brightpath.example: assign to Jade and tag 'Jade'."

---

## 0. The one idea that organizes everything

> **The model only extracts. The code decides.**

v1 was a single prompt asked to do five jobs at once: understand the request, know the rule vocabulary, decide if anything was missing, ask good questions, and format the answer. It hit 30/36, and every failure was the same species: a *policy* miss (built when it should have asked, asked when it should have built, or invented a tag name). Three rounds of sterner prompt rules could not fix it, because a prompt is a request, not a constraint.

v2 splits the five jobs across two very different workers:

| Job | Who does it | Why |
|---|---|---|
| Map words to vocabulary | LLM (`extract.py`) | Language understanding is the one thing only a model can do |
| Know what's legal | Code (`schema.py`) | Enums and compatibility matrices should never be paraphrased |
| Decide complete / missing / invented | Code (`validator.py`) | Judgment you can write as `if` statements should be `if` statements |
| Decide what to ask, and when | Code (`validator.py`) | Question policy was v1's top failure class |
| Render the reply | Code (`copilot.py`) | Deterministic formatting, exact-match gradable |

The consequence: the copilot *cannot* emit an illegal rule, and it *cannot* invent a value. At worst it emits a wrong-but-legal one, and the eval catches that by exact match.

---

## 1. The cast (five files)

```
user message(s)
     │
     ▼
extract.py      the ONLY LLM call: conversation -> partial rule spec (strict JSON)
     │
     ▼
validator.py    pure code: legality, completeness, provenance -> verdict + questions
     │
     ▼
copilot.py      renders: draft with holes, questions, or final WHEN/IF/THEN + JSON
     │
     ▼
grader.py       (eval only) canonicalize + diff against the real admin-built rule
```

`schema.py` sits underneath all of them: 7 triggers, 15 condition properties each with its own operator list, 10 actions each with required params. It is the single source of truth, and it was derived from the 90-day prod dump, so "validates against schema.py" means "buildable in prod."

---

## 2. Step 1: extraction (the only LLM call)

`extract.py` sends gpt-4o three things: a system prompt containing the legal vocabulary plus 8 extraction rules, the conversation so far, and a **strict JSON schema** for the response (`response_format: json_schema, strict: true`).

Strict structured output is the first big concept: the API *guarantees* the reply parses against the schema. The trigger literally cannot be a string outside the 7 legal names; an action type cannot be anything but the 10 known types. A whole class of failure (malformed or off-vocabulary output) is eliminated before any of our code runs.

What came back for rw-020, verbatim:

```json
{
  "intent_summary": "Assign emails addressed or CC'd to jade@brightpath.example to Jade and tag them 'Jade'.",
  "trigger": "new_conversation_inbound",
  "scope_confirmed": true,
  "condition_groups": [
    [
      {"property": "to", "op": "contains", "values": ["jade@brightpath.example"]},
      {"property": "cc", "op": "contains", "values": ["jade@brightpath.example"]}
    ]
  ],
  "actions": [
    {"type": "assign", "target": "Jade", ...nulls...},
    {"type": "add_tag", "tags": ["Jade"], ...nulls...}
  ],
  "unsupported_requests": []
}
```

Four quiet decisions in there, each encoded as a numbered extraction rule that exists because an eval run failed without it:

1. **Trigger = `new_conversation_inbound`** even though the user never said "when a new conversation arrives." Rule 4: default to inbound when unstated, because 82% of prod rules are inbound. The first v2 run *asked* about the trigger instead and over-questioned on 13/40 fully-specified requests. The fix: assume the statistically dominant answer and *disclose the assumption* in the draft. Assumptions are disclosed, not asked.
2. **`to` and `cc` are in the same group.** Condition semantics: groups are AND'd, conditions inside a group are OR'd. "Addressed to or CC'd to" is an OR, so one group, two conditions. Rule 2 teaches the model this mapping ("or" = same group, "and" = separate groups).
3. **Operator is `contains`, not `is`.** Rule 8: to/cc headers can hold several addresses, so "addressed to X" is always `contains`; `is` only when the user says "exactly." This rule was added in v2.3 and fixed 5 records that a careless few-shot example had broken in v2.2 (the example primed `is`). Lesson: examples leak; the model imitates whatever you show it.
4. **`scope_confirmed: true`** because a condition was given. Rule 3: bare plurals ("incoming emails") do not count as "run on everything"; a condition or an explicit all/every does.

Note what the model did **not** do: it didn't judge whether the rule was finished, didn't plan questions, didn't format anything. Slot-filling only.

## 3. Step 2: the validator (pure code, no LLM)

`validator.py` takes the spec plus the raw conversation text and returns a verdict. For rw-020:

```json
{"status": "complete", "errors": [], "missing": [], "hallucinated": [],
 "unsupported": [], "questions": [], "questions_pending": 0}
```

Boring, and that's the point. The interesting part is what it *would* have caught. Five separate gates:

- **errors**: unknown property, operator not in that property's list, trigger x condition incompatibility (e.g. `hours_passed_since` only works on outgoing triggers). These mean extraction bugs, and the status becomes `invalid`.
- **missing**: required-but-empty slots. No trigger, a text condition with no values, an `add_tag` with no tags. Each missing slot carries its own pre-written question (defined next to the param in `schema.py`, so the question and the requirement can never drift apart).
- **hallucinated**: the provenance gate, section 5 below.
- **unsupported**: asks we recognize but don't build (connectors, custom fields, SLAs). Named to the user, never silently dropped, never faked.
- **question planning**: bundle at most 3 questions per turn, ordered trigger, then scope, then action params. This is *policy as code*: v1's worst failure class (when to ask vs when to build) is now a sort key and a slice, not a prompt exhortation.

Status is a three-way switch: `invalid` / `needs_info` / `complete`. That switch, not the model's mood, decides what the user sees.

## 4. Steps 3 and 4: rendering and the final rule

`copilot.py` renders deterministically from the spec + verdict. Status was `complete`, so:

```
WHEN  new_conversation_inbound — a new conversation arrives (started by the customer)
IF    (to contains 'jade@brightpath.example'  OR  cc contains 'jade@brightpath.example')
THEN  1. assign to 'Jade'
      2. add tag 'Jade'
```

plus the machine JSON (`to_final_json`), which is the grader- and prod-compatible shape. Had the status been `needs_info`, the same renderer would have shown the closest legal draft with `⟨required — not provided yet⟩` holes and the planned questions. Showing the draft with holes matters: the user always sees exactly what the system believes so far, so a misunderstanding surfaces one turn early, not at the end.

## 5. Step 5: grading against the real admin

The grader canonicalizes both rules (the engine's vocabulary and the raw prod dump's vocabulary map into one comparison form) and diffs per slot:

```json
{"trigger": {"match": true},
 "conditions": {"precision": 1.0, "recall": 1.0},
 "actions":    {"precision": 1.0, "recall": 1.0},
 "strict_pass": true}
```

The copilot built, from one English sentence, structurally the same rule a real Hiver admin clicked together in the builder. That sentence-to-parity diff is the entire eval, repeated 40 times per run.

Two design choices worth internalizing:

- **Runner and grader are separate.** Model outputs are captured once (`run_eval.py`), grading is re-runnable for free (`grader.py`, `report.py`). When a grader bug is found, you fix it and re-score every historical run without spending a single API call. Every run file carries engine/model/prompt-sha, so numbers stay comparable forever.
- **Three grading tiers.** Tier 1: did it emit parseable JSON at all. Tier 2: deterministic structural diff (this is 95% of the signal). Tier 3: an LLM judge, but *only* for the handful of diffs flagged possibly-equivalent (`is` vs `contains` on a full email address). Judges are expensive and fuzzy, so they get the smallest possible jurisdiction.

---

## 6. The clarification loop, live (Demo B)

Same target rule, but opened vague, the way real admins talk:

> **Turn 1, user:** "we get a lot of emails meant for jade, can you route them to her?"

Extraction returned: trigger defaulted to inbound, no conditions, `scope_confirmed: false`, **no actions**, and (this is the wart) it filed "route emails to Jade" under `unsupported_requests` instead of mapping it to an `assign` action. That is a genuine extraction miss on today's live run.

Now watch the architecture absorb the miss. The validator doesn't care why slots are empty; it reports:

```
status: needs_info
missing: scope, actions
questions:
  1. Should this run on every matching conversation, or only some? ...
  2. What should happen when this fires — tag, assign, change status, ...?
```

> **Turn 2, user:** "anything addressed to or cc'd to jade@brightpath.example. assign it to Jade and also add the tag Jade."

Key mechanic: extraction re-runs over the **whole conversation**, not the last message. There is no fragile state-merging code; the accumulated state *is* the transcript, re-read fresh each turn. Result: `status: complete`, and the grader says `strict_pass: true` against the same prod rule. Two turns, vague opening, exact match.

The wart is worth remembering when reading eval numbers: single-turn strict match measures extraction; the loop's job is to *converge despite* imperfect extraction. That is also why the multi-turn simulator exists, and it's why "36/40 single-turn" and "9/10 multi-turn" are different claims about different properties.

## 7. The provenance gate (Demo C, no LLM involved)

The single most important rule in the system, and it's four lines of code. Feed the validator a spec claiming `add_tag: ["VIP"]` when the user only ever said "tag all incoming emails":

```
hallucinated: [{slot: actions[0].tags, value: 'VIP', question: 'Which tag(s) should I apply?'}]
after scrub:  tags = []
re-ask:       'Which tag(s) should I apply?'
```

The rule: **every free-text value (tag, person, keyword, address, inbox) must literally appear in the user's own messages.** Not "should," must: it's a substring check, `_in_convo()`. A value the user never typed gets scrubbed from the spec and converted into a question.

This one gate killed v1's worst bug, the invented "VIP" tag leaking out of few-shot examples, which three rounds of prompt engineering ("NEVER invent tag names") could not kill. The general principle: **when a model keeps breaking a rule, stop rewriting the rule and build a gate the output must pass through.** Prompts are requests; validators are laws.

Its companion is the META_VALUES guard: when the copilot asks "should I match specific senders?" and the user echoes "yes, match on specific senders," the phrase "specific senders" is mechanism-language, not a value. The simulator found that bug on day one; the fix is a blocklist. Note who found it: not a human tester, the self-play harness.

---

## 8. The concepts, named

What each piece of this repo is called in the general copilot-building vocabulary:

| In this repo | The general concept |
|---|---|
| `schema.py` from the prod dump | **Grounding**: vocabulary from the source of truth, not from docs or model memory |
| Strict `response_format` in `extract.py` | **Structured output**: schema-constrained generation |
| The 8 numbered extraction rules | **Prompt engineering**, in its right place: nuance the schema can't express |
| `validator.py` | **Guardrails as code**: legality, completeness, and policy outside the model |
| Provenance + META_VALUES | **Anti-hallucination gating**: verifiable claims checked mechanically |
| Question planning + MAX_QUESTIONS | **Dialogue policy**: when to ask, what, how much, as code |
| Re-extract over full history | **Stateless turn architecture**: transcript as the only state |
| eval set mined from prod | **Eval-driven development**: every change is a scored run, ratchet up |
| runner/grader split, prompt-sha in runs | **Reproducibility**: re-grade for free, compare across months |
| Tier-3 judge on flagged diffs only | **LLM-as-judge**, minimized jurisdiction |
| `simulate.py` self-play | **Agent simulation**: synthetic users to test the loop before real ones |

And the run history is the honest version of the story: v2's *first* run scored 16/40, far below v1's 27, because it over-asked. The architecture didn't win on day one; the eval told it what to fix (trigger default, OR-grouping, operator choice), and three scored iterations later it was at 36/40. The system is the loop, not the prompt.

## 9. Where the 4 remaining misses live

- rw-004: "any direction" trigger ambiguity (genuinely ambiguous English).
- rw-010, rw-015, rw-034: `is` vs `contains` equivalences on full addresses, waiting on the Tier-3 judge (one has a stray apostrophe in the prod source data itself).
- Plus the one sim miss: AND vs OR linkage when conditions arrive across separate turns. The right fix is to make it an explicit question, which is a validator change, not a prompt change. Notice the pattern.

## 10. What this sets up

You can now read every file in `engine/` and know why it exists. The next milestones each add exactly one new concept on top:

1. **ai_extract support** (275 prod rules): schema evolution, i.e. growing the legal vocabulary without breaking the 40 records that already pass.
2. **Entity validation via tool calling**: the copilot asks the workspace "does a 'refund' tag exist?" instead of trusting the user's spelling. The one core concept this repo hasn't touched.
3. **Multi-turn eval records**: promote the simulator's findings into permanent, scored ground truth.
