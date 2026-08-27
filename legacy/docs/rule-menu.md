# Automation Copilot v2 — The Rule Menu (draft v2)

The single source of truth for what the assistant may build. Scope: **conversation-type triggers only** (Milestone-1 parity scope). Everything the assistant outputs must validate against this document.

**Legend:**
- ✅ verified — from live builder screenshots (2026-07-07) or the Automation Parity Confluence doc (M1 tables)
- ⚠️ GAP — missing or ambiguous; needs Mithil to confirm from the live builder
- 📜 2023-spec — from the Advanced Automations Google Doc (HiG-era); unverified for the current builder

**Sources:**
- Builder screenshots (2026-07-07): trigger dropdown, condition dropdown, and per-condition operator dropdowns ✅
- Confluence: [Automation Parity (Hiver Gmail ↔ Hiver Omni)](https://hiverhq.atlassian.net/wiki/spaces/PRODUCT/pages/1434484746) — M1 scope
- Google Doc: Advanced Automations spec (2023)

**Scope exclusions (confirmed by Mithil):**
- `matches a row in` operator — Custom Objects; ignore for this milestone
- Custom Fields, AI Variable, API Variable conditions — proposed exclusion.
  **Resolved 2026-08-09:** AI Variable confirmed excluded from pilot scope — AI-based
  automation building is a separate team's project; the two merge in production. The
  engine's ai_extract support (v2.4) stays as a built-but-gated extension. Custom
  Fields remain excluded (next unlock candidate per the coverage analysis).
- `contains any value from` operator (seen on Subject, tagged "New") — ⚠️ looks Custom-Object-related like "matches a row in"; assumed excluded, confirm

---

## 1. Rule shape

```
rule
├── trigger           — exactly one
├── condition groups  — zero or more groups.
│                       Rows INSIDE a group are joined by OR (“+ OR condition”).
│                       Groups are joined by AND (“+ AND condition”).
│                       ✅ observed in builder — confirm reading is right ⚠️
└── actions           — one or more
```

Each condition row = **(field, operator, value)**. Empty value → builder error "Please remove this condition or enter a value" ✅.

Behavioral guardrails (📜 2023-spec, likely still true — confirm):
- One trigger per rule.
- Multiple rules can apply to one conversation.
- An automation action cannot trigger another automation (no chaining/loops).
- Autoresponder replies never trigger automations.
- Rules live per shared inbox. (M1 adds cross-mailbox actions — see Add/Remove Conversation.)

---

## 2. Triggers ✅ (builder screenshot)

| # | Trigger | Group |
|---|---|---|
| T1 | New conversation (inbound) is received | New conversation |
| T2 | New conversation (outbound) is sent | New conversation |
| T3 | New conversation (inbound or outbound) is created | New conversation | ← confirmed legal by Mithil, 2026-08-09 (613 organic uses in the 90d dump) |
| T4 | Conversation is moved to this Shared Inbox | New conversation |
| T5 | External reply is received from anyone | Reply |
| T6 | External reply is received from the contact | Reply |
| T7 | Mailbox reply is sent | Reply |
| T8 | Assignee is changed | State change |
| T9 | Tag(s) is added | State change |
| T10 | Tag(s) is removed | State change |

---

## 3. Conditions and operators

### 3.1 Email-field and text conditions ✅ (operator dropdowns, builder screenshots 2026-07-07)

`matches a row in` (Custom Objects) omitted everywhere per scope decision.

| Condition | Operators | Input |
|---|---|---|
| From Email | is · is not · contains any of · does not contain · matches | "Enter keyword(s)" free text |
| From Domain | is | "Enter keyword(s)" free text |
| To Email | contains any of · does not contain | free text |
| To Domain | contains any of · does not contain | free text |
| Cc | contains any of · does not contain | free text |
| Bcc Email | is · is not · contains any of · does not contain · matches | "Enter keyword(s)" free text |
| Bcc Domain | contains any of · does not contain | free text |
| Reply-to Email | contains any of · does not contain | free text |
| Reply-to Domain | is | "Enter keyword(s)" free text |
| Subject | is · is not · contains any of · does not contain · matches | free text (also shows `contains any value from` — excluded, see scope) |
| Body | contains any of · does not contain | "Enter keyword(s)" free text |

Notable asymmetries (verified, not typos — the builder really differs per field):
- From Email and Bcc Email get the full operator set incl. `is not` and `matches`; To/Cc/Reply-to Email only get contains-style operators.
- From Domain and Reply-to Domain support only exact `is`; To Domain and Bcc Domain only contains-style.

⚠️ GAP: semantics of `matches` (exact match? wildcard? regex?) — check the ⓘ tooltip or KB.
⚠️ GAP: do keyword inputs accept multiple comma-separated values (assumed for "contains any of")?

### 3.2 Time/date conditions ✅ (builder screenshots + Confluence §3.2)

**Creation Time**
| Operator | Input |
|---|---|
| is within / is outside | start + end time (hours:minutes) + timezone selector (default = Analytics timezone) |
| is within business hours / is outside business hours | none (greyed out if no business hours applied to the inbox) |

**Time Passed Since**
| Operator | Input |
|---|---|
| No external reply received is | number + hrs/mins, "Count in business hours only" checkbox |
| No change in status is | same |
| No change in assignee is | same |
| No change in tags is | same |

(Builder confirms **4** operators — Confluence §3.2 listed only 3; "No external reply received is" is real. Hours ≤999, minutes ≤59 per Confluence.)

**Date**
| Operator | Input |
|---|---|
| is on / is before / is after | single date (DD MMM, YYYY), ≤2 years out, + timezone |
| is between | start + end date + timezone |

**Day**
| Operator | Input |
|---|---|
| is any of | multi-select checkboxes Monday–Sunday |

### 3.3 Conversation-state conditions (✅ operators from Confluence §3.2; ⚠️ no builder screenshots yet)

**Assignee** ✅
| Operator | Input |
|---|---|
| Is / Is not | single-select: mailbox users, "Unassigned" first |
| Is any of / Is none of | multi-select: users + Unassigned, "Select all" option |

**Tags** (operators ✅, input ⚠️)
| Operator | Input |
|---|---|
| Is any of / Is all of / Is none of | ⚠️ presumably multi-select of mailbox tags (+ "no tag applied"? per 2023 spec) — screenshot needed |

**Status** 📜 ⚠️
| Operator | Input |
|---|---|
| Is / Is any of / Is not (2023 spec) | Open, Pending, Closed (2023 spec) — confirm current operators + values in builder |

---

## 4. Actions ✅ (builder screenshots 2026-07-07)

11 actions confirmed live in the builder. "Custom object column" options inside the pickers are excluded per scope decision. The builder **disproves** the Confluence Future-Scope labels on Add Followers (§3.3.2) and Add a Note (§3.3.4) — both are live.

| Action | Parameters (✅ from builder) |
|---|---|
| Assign to | Single-select from mailbox users; first option **None** (= unassign). |
| Assign among | Multi-select users (checkboxes, type-ahead) + distribution method dropdown — **Load Balancing** seen ✅; ⚠️ confirm Round Robin is the other option (per Confluence §3.3.1). |
| Add followers | Multi-select users with Select All. |
| Update status | Single-select: **Open · Pending · Closed**. |
| Add tag(s) | Multi-select mailbox tags with Select All. |
| Remove tag(s) | Multi-select mailbox tags. (📜 silently skips tags not applied.) |
| Send a reply | Opens "Send a reply email" modal: **Send from** (default "Assignee (if any)"; ⚠️ other options unexpanded — Confluence says mailbox address + specific members), **To** (default "Contact only"; ⚠️ unexpanded — Confluence says "all participants from last reply" is the alternative), rich-text body with **{{ Variable }}** insertion, **Include CSAT snippet** toggle (disabled when CSAT off). Validation: reply email required. |
| Send notification | Multi-select users + **"Also send email"** checkbox. |
| Add a note | Free-text body; supports **@mention** to notify users and **{{ }}** extracted-data variables; **"Pin this note"** checkbox. |
| Add conversation to | Single-select target shared inbox. |
| Remove conversation | No parameters. |

⚠️ GAP: the action *dropdown itself* wasn't captured — confirm these 11 are the complete list (no "set custom field" or other entries beyond scope exclusions).

Excluded: Custom Fields (set), Trigger Approval (future scope), Custom-object columns in any picker.

---

## 5. Compatibility matrix (trigger × condition)

✅ = confirmed · ⚠️ = to verify · ✗ = not compatible (per Confluence §3.1 per-trigger tables)

The 15 operator screenshots (§3.1–3.2 above) all come from one trigger's builder session — ⚠️ GAP: which trigger was open? (assumed T1 inbound). The earlier condition-dropdown screenshots for that trigger showed, in order: From Email, From Domain, To Domain, To Email, Cc, Bcc Email, Bcc Domain, Reply-to Email, Reply-to Domain, Subject, Body, AI Variable, API Variable (greyed), Creation Time, Time Passed Since, Date, Day — with **no Status/Assignee/Tags**, consistent with the 2023 spec ("Status/Assignee/Tags not on new-conversation triggers"). ⚠️ confirm the list wasn't cut off after "Day".

| Condition | T1 inbound | T2 outbound | T3 in-or-out | T4 moved | T5 ext reply anyone | T6 ext reply contact | T7 mailbox reply | T8 assignee chg | T9 tag added | T10 tag removed |
|---|---|---|---|---|---|---|---|---|---|---|
| From Email / Domain | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ likely | ✅ | ⚠️ | ✗ | ✗ | ✗ |
| To Email / Domain | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ likely | ✅ | ⚠️ | ✗ | ✗ | ✗ |
| Cc | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ likely | ✅ | ⚠️ | ✗ | ✗ | ✗ |
| Bcc Email / Domain | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✗ | ✗ | ✗ |
| Reply-to Email / Domain | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✗ | ✗ | ✗ |
| Subject | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| Body | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✗ | ✗ | ✗ |
| Status | ✗ (2023 spec + absent from dropdown) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| Tags | ✗ (same) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| Assignee | ✗ (same) | ⚠️ | ⚠️ | ⚠️ | ✅ (§3.2) | ✅ | ✅ (§3.2) | ✅ | ✅ | ✅ |
| Creation Time | ✅ | ✅ (§3.2) | ✅ (§3.2) | ⚠️ | ✅ (§3.2) | ✅ | ✅ (§3.2) | ✗ | ✗ | ✗ |
| Time Passed Since | ✅ | ✅ (§3.2) | ✅ (§3.2) | ⚠️ | ✅ (§3.2) | ✅ | ✅ (§3.2) | ✅ | ✅ | ✅ |
| Date | ✅ | ✅ (§3.2) | ✅ (§3.2) | ⚠️ | ✅ (§3.2) | ✅ | ✅ (§3.2) | ✅ | ✅ | ✅ |
| Day | ✅ | ✅ (§3.2) | ✅ (§3.2) | ⚠️ | ✅ (§3.2) | ✅ | ✅ (§3.2) | ✅ | ✅ | ✅ |

**✗ on T8–T10** = Confluence §3.1.1–3.1.3 per-trigger tables (only Subject, Status, Tags, Assignee, Time Passed Since, Date, Day + Custom Fields). **Known contradiction:** §3.2's applicable-triggers column also lists From Domain / Reply-to Domain on state-change triggers. ⚠️ Mithil to adjudicate — assumed per-trigger tables win.

**T4 (moved to Shared Inbox)**: still zero documentation — entire column ⚠️.

Trigger × **action**: Confluence marks Assign Among / Add-Remove Conversation as "ALL"; per-trigger action lists for T6, T8–T10 are identical. ⚠️ Assume all actions valid on all 10 triggers unless the builder shows otherwise.

---

## 6. Remaining open questions

1. Which trigger were the condition screenshots taken on, and was the condition list complete after "Day"? Then: condition dropdowns for T2, T3, T4, T5, T7 (T4 especially — fully undocumented).
2. Tags condition input + current Status condition operators/values (screenshot on a state-change trigger, e.g. Tag added).
3. Action dropdown menu itself — confirm the 11 actions in §4 are the complete list.
4. Assign among: confirm distribution options = Round Robin + Load Balancing.
5. Send a reply: expand the **Send from** and **To** dropdowns to capture all options.
6. Semantics of the `matches` operator (wildcard? regex? exact?).
7. Confirm `contains any value from` is Custom-Object-related → excluded.
8. Adjudicate §3.1 vs §3.2 contradiction (From/Reply-to Domain on state-change triggers).
9. Confirm AND/OR reading: rows within a block = OR; blocks = AND.
10. Plan gating, if the assistant should handle it in v1.
