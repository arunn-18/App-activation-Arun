"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchPreview } from "@/lib/api";
import type {
  Action,
  Condition,
  ConnectorTestRun,
  ConnectorTestRunStep,
  NativeActionTestRun,
  RulePreview,
  Spec,
  TurnState,
  Vocabulary,
} from "@/lib/api";

function Keyword({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block w-14 shrink-0 font-mono text-[11px] font-semibold tracking-[0.14em] text-ink-soft">
      {children}
    </span>
  );
}

function Hole({ hint }: { hint: string }) {
  return (
    <span className="rounded-sm border border-dashed border-ink-soft/60 bg-bone px-1.5 py-0.5 font-mono text-[12px] text-ink-soft">
      {hint}
    </span>
  );
}

function Value({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-sm bg-bone px-1.5 py-0.5 font-mono text-[12px] text-ink">
      {children}
    </span>
  );
}

/** The scope-assumption row: the chosen reading stated inline, with the
 *  everything-vs-subset fork opened ON DEMAND (the Claude permission-prompt
 *  pattern: a compact button row, never a one-option radio group). Both
 *  choices COMPOSE A CHAT MESSAGE — answers travel through the conversation. */
function ScopeAssumed({
  onAnswer,
  disabled,
}: {
  onAnswer?: (text: string) => void;
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [subset, setSubset] = useState(false);
  const [text, setText] = useState("");
  const canAct = !!onAnswer && !disabled;

  const sendSubset = () => {
    const t = text.trim();
    if (!t) return;
    onAnswer?.(/^only\b/i.test(t) ? t : `only ${t}`);
  };

  if (!editing || !canAct) {
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <span className="text-[13px] text-ink">every incoming conversation</span>
        <span className="rounded-full border border-dashed border-ink-soft/50 px-2 py-0.5 text-[11px] text-muted-foreground">
          assumed
        </span>
        {canAct && (
          <button
            onClick={() => setEditing(true)}
            className="text-[12px] font-medium text-ink underline underline-offset-2 hover:text-ink-soft"
          >
            narrow it
          </button>
        )}
      </span>
    );
  }

  return (
    <span className="flex flex-col gap-2">
      <span className="inline-flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="text-[12px]"
          onClick={() => onAnswer?.("run it on every matching conversation")}
        >
          Every incoming conversation
        </Button>
        <Button
          variant={subset ? "default" : "outline"}
          size="sm"
          className="text-[12px]"
          onClick={() => setSubset(true)}
        >
          Only a subset…
        </Button>
        <button
          onClick={() => {
            setEditing(false);
            setSubset(false);
          }}
          className="text-[12px] text-muted-foreground hover:text-ink"
        >
          cancel
        </button>
      </span>
      {subset && (
        <span className="flex items-center gap-2">
          <Input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendSubset()}
            placeholder="senders or subject/body keywords to match"
            className="h-8 flex-1 text-[13px]"
          />
          <Button size="sm" disabled={!text.trim()} onClick={sendSubset}>
            Apply
          </Button>
        </span>
      )}
    </span>
  );
}

function ConditionLine({ c, vocab }: { c: Condition; vocab?: Vocabulary }) {
  const name =
    c.property === "ai_variable"
      ? `AI:${c.variable ?? "?"}`
      : (vocab?.properties[c.property] ?? c.property);
  const noValues = !["exists", "does_not_exist"].includes(c.op);
  return (
    <span className="inline-flex flex-wrap items-baseline gap-1.5">
      <span className="font-mono text-[12px] font-medium text-ink-soft">{name}</span>
      <span className="font-mono text-[12px] text-muted-foreground">{c.op}</span>
      {noValues &&
        (c.values.length ? (
          c.values.map((v, i) => <Value key={i}>{v}</Value>)
        ) : (
          <Hole hint="value?" />
        ))}
    </span>
  );
}

function ActionLine({ a }: { a: Action }) {
  const need = (v: string | null | undefined, hint: string) =>
    v ? <Value>{v}</Value> : <Hole hint={hint} />;
  const needList = (v: string[] | null | undefined, hint: string) =>
    v?.length ? v.map((x, i) => <Value key={i}>{x}</Value>) : <Hole hint={hint} />;
  switch (a.type) {
    case "add_tag":
      return <>add tag {needList(a.tags, "which tag?")}</>;
    case "remove_tag":
      return <>remove tag {needList(a.tags, "which tag?")}</>;
    case "assign":
      return <>assign to {need(a.target, "who?")}</>;
    case "assign_among": {
      const how =
        a.distribution === "round_robin"
          ? "round robin"
          : a.distribution === "load_balancing"
            ? "load balancing"
            : null;
      return (
        <>
          assign among {needList(a.targets, "which people?")} by{" "}
          {how ? <Value>{how}</Value> : <Hole hint="round robin or load balancing?" />}
        </>
      );
    }
    case "status":
      return <>set status to {need(a.status_value, "open / pending / closed?")}</>;
    case "add_note":
      return (
        <>
          add note {need(a.content, "what should it say?")}
          {a.pinned ? <span className="text-muted-foreground"> (pinned)</span> : null}
        </>
      );
    case "send_mail":
      return <>send reply {need(a.body_hint, "saying what?")}</>;
    case "send_notification":
      return <>notify the team{a.email_enabled ? " (email + in-app)" : ""}</>;
    case "add_to_sm":
      return <>add to shared inbox {need(a.inbox, "which inbox?")}</>;
    case "remove_from_sm":
      return <>remove from this shared inbox</>;
    case "connector": {
      // native_action_id (v2.12, capability 5) is Hiver's own pre-built
      // action block — no chain, no test_contact_email, just its two
      // generic slots. Same "no vocabulary endpoint yet" fallback as the
      // recipe id below: hardcode the one known id's display name.
      if (a.native_action_id) {
        const nativeLabel = a.native_action_id === "clickup_create_task"
          ? "Create tasks automatically via automation"
          : a.native_action_id;
        return (
          <>
            run native action — {nativeLabel}, target{" "}
            {need(a.target_name, "which list/board/channel?")}, titled{" "}
            {need(a.title_hint, "what should it be titled?")}
          </>
        );
      }
      // recipe is a raw id (engine/schema.py RECIPES key) — the engine has no
      // vocabulary endpoint for recipe display names yet (only trigger/
      // property labels, via /api/vocabulary), so this falls back to the id
      // itself rather than inventing a lookup the backend doesn't serve. A
      // custom_plan (v2.11) has no id at all — it names itself via
      // plan_summary, the model's own plain-English description.
      const recipeLabel = a.custom_plan
        ? `dynamically-composed plan — ${a.custom_plan.plan_summary}`
        : a.recipe === "salesforce_account_csm_autoassign"
          ? "Auto-assign to the account's CSM (Salesforce)"
          : a.recipe;
      const terminalLine = a.assigns_to
        ? <> → then assign the conversation to <span className="font-mono">{a.assigns_to}</span> (extracted from Salesforce)</>
        : a.tags_with
          ? <> → then tag the conversation with <span className="font-mono">{a.tags_with}</span> (extracted from Salesforce)</>
          : null;
      return (
        <>
          run connector recipe — {need(recipeLabel, "which recipe?")}, test with{" "}
          {need(a.test_contact_email, "a real contact email?")}
          {terminalLine}
        </>
      );
    }
    default:
      return <>{a.type}</>;
  }
}

/** Proof a connector rule does something real, before it's marked done: the
 *  engine already RAN the recipe's chain (or fired the native action)
 *  against the test contact email — or, for a native action, with no test
 *  contact at all (engine/executor.py, via copilot.connector_test_run) —
 *  this renders that result, it doesn't trigger a call of its own.
 *  "no_match" (e.g. the test account has no CSM) is a clean, honest outcome
 *  for a chain-based result, styled like the zero-match case in
 *  PreviewStrip below, not an error; a native action has no such outcome —
 *  see NativeActionTestRunStrip. */
function TestRunStrip({ testRun }: { testRun: ConnectorTestRun | NativeActionTestRun }) {
  if ("result" in testRun) return <NativeActionTestRunStrip testRun={testRun} />;
  return <ChainTestRunStrip testRun={testRun} />;
}

/** The native-action shape (capability 5) has no steps/final to expand —
 *  it either ran or it didn't, so this is a single line, no "see steps". */
function NativeActionTestRunStrip({ testRun }: { testRun: NativeActionTestRun }) {
  if (testRun.status === "ok") {
    const url = typeof testRun.result?.url === "string" ? testRun.result.url : null;
    return (
      <div className="border-b border-hairline px-5 py-2.5">
        <span className="text-[12.5px] text-ink-soft">
          <span className="font-medium text-ink">Test run: done</span>
          {url ? <> — <span className="font-mono text-[12px]">{url}</span></> : null}.
        </span>
      </div>
    );
  }
  return (
    <div className="border-b border-hairline bg-destructive-soft px-5 py-2.5">
      <span className="text-[12.5px] text-destructive">
        <span className="font-semibold">Test run: couldn&apos;t complete</span>
        {testRun.reason ? ` — ${testRun.reason}.` : "."}
      </span>
    </div>
  );
}

function ChainTestRunStrip({ testRun }: { testRun: ConnectorTestRun }) {
  const [open, setOpen] = useState(false);

  if (testRun.status === "ok" && testRun.final)
    return (
      <div className="border-b border-hairline px-5 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[12.5px] text-ink-soft">
            {testRun.final.type === "assign" ? (
              <>
                <span className="font-medium text-ink">Test run: assigned to</span>{" "}
                <span className="font-mono text-[12px]">{testRun.final.target}</span>.
              </>
            ) : (
              <>
                <span className="font-medium text-ink">Test run: tagged with</span>{" "}
                <span className="font-mono text-[12px]">{testRun.final.tags.join(", ")}</span>.
              </>
            )}
          </span>
          <button
            onClick={() => setOpen((o) => !o)}
            className="shrink-0 text-[12px] font-medium text-ink underline underline-offset-2 hover:text-ink-soft"
          >
            {open ? "hide steps" : "see steps"}
          </button>
        </div>
        {open && <TestRunSteps steps={testRun.steps} />}
      </div>
    );

  return (
    <div className="border-b border-hairline bg-destructive-soft px-5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12.5px] text-destructive">
          <span className="font-semibold">
            Test run: nothing happened
          </span>
          {testRun.reason ? ` — ${testRun.reason}.` : "."}
        </span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 text-[12px] font-medium text-destructive underline underline-offset-2"
        >
          {open ? "hide steps" : "see steps"}
        </button>
      </div>
      {open && <TestRunSteps steps={testRun.steps} />}
    </div>
  );
}

function TestRunSteps({ steps }: { steps: ConnectorTestRunStep[] }) {
  return (
    <div className="mt-2 flex flex-col gap-1.5 border-l-2 border-hairline pl-3">
      {steps.map((s, i) => (
        <p key={i} className="font-mono text-[11px] leading-relaxed text-ink-soft">
          {s.kind === "api_call" ? (
            <>
              {s.op}({JSON.stringify(s.args)}) →{" "}
              {s.response?.totalSize ?? 0} record
              {s.response?.totalSize === 1 ? "" : "s"}
            </>
          ) : s.kind === "assign" ? (
            <>assign → {s.target}</>
          ) : (
            <>add_tag → {(s.tags ?? []).join(", ")}</>
          )}
        </p>
      ))}
    </div>
  );
}

/** Blast radius before the rule exists: replay the draft over last week's
 *  mail. "All 189 of 189" makes an everything-scope viscerally checkable;
 *  a subset shows its real count plus example matches. Honest when it can't
 *  run (AI conditions, time windows): states why, never approximates. */
function PreviewStrip({ rule }: { rule: object }) {
  const [pv, setPv] = useState<RulePreview | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const key = JSON.stringify(rule);

  useEffect(() => {
    let live = true;
    setPv(null);
    setFailed(false);
    fetchPreview(JSON.parse(key)).then(
      (r) => live && setPv(r),
      () => live && setFailed(true)
    );
    return () => {
      live = false;
    };
  }, [key]);

  if (failed) return null; // preview is an enhancement, never a blocker
  if (!pv)
    return (
      <div className="border-b border-hairline px-5 py-2.5 text-[12px] text-muted-foreground">
        Dry run against last week&rsquo;s mail…
      </div>
    );
  if (!pv.previewable)
    return (
      <div className="border-b border-hairline px-5 py-2.5 text-[12px] text-muted-foreground">
        Can&rsquo;t dry-run this rule: {pv.reason}.
      </div>
    );

  const all = pv.matched === pv.total;
  if (pv.matched === 0)
    return (
      <div className="border-b border-hairline bg-destructive-soft px-5 py-2.5 text-[12.5px] text-destructive">
        This would have matched <span className="font-semibold">none</span> of
        the {pv.total} conversations from the last {pv.window_days} days — the
        conditions may not describe real mail. Say what to adjust, or create it
        anyway.
      </div>
    );
  return (
    <div className="border-b border-hairline px-5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12.5px] text-ink-soft">
          <span className="font-medium text-ink">
            Would have matched {all ? `all ${pv.total}` : `${pv.matched} of ${pv.total}`}
          </span>{" "}
          conversations from the last {pv.window_days} days.
        </span>
        {(pv.sample?.length ?? 0) > 0 && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="shrink-0 text-[12px] font-medium text-ink underline underline-offset-2 hover:text-ink-soft"
          >
            {open ? "hide examples" : "see examples"}
          </button>
        )}
      </div>
      {open && (
        <div className="mt-2 flex flex-col gap-1 border-l-2 border-hairline pl-3">
          {pv.sample!.map((s, i) => (
            <p key={i} className="text-[12px] text-ink-soft">
              <span className="font-mono text-[11px] text-muted-foreground">
                {s.from}
              </span>{" "}
              — {s.subject}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

const STATUS_STYLE: Record<TurnState["status"], string> = {
  complete: "bg-bone text-ink",
  needs_info: "bg-bone text-ink-soft",
  invalid: "bg-destructive-soft text-destructive",
};
const STATUS_LABEL: Record<TurnState["status"], string> = {
  complete: "Complete — buildable rule",
  needs_info: "In progress — needs answers",
  invalid: "Couldn't map",
};

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-3 border-b border-hairline py-3 last:border-b-0">
      <Keyword>{k}</Keyword>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5 text-[13px] leading-relaxed">
        {children}
      </div>
    </div>
  );
}

/** Inline rule card, one per copilot turn — the Amplitude embedded-result
 *  pattern. Only the latest card carries the apply actions; earlier cards
 *  stay in the transcript as the reasoning trail. */
export default function RuleCard({
  turn,
  isLatest,
  applied,
  onApply,
  vocab,
  onAnswer,
  disabled,
}: {
  turn: TurnState;
  isLatest: boolean;
  applied: boolean;
  onApply: () => void;
  vocab?: Vocabulary;
  onAnswer?: (text: string) => void;
  disabled?: boolean;
}) {
  const [showJson, setShowJson] = useState(false);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const spec: Spec = turn.spec;
  const groups = spec.condition_groups ?? [];
  const aiVars = spec.ai_extract?.variables ?? [];
  const scopeAssumption = (turn.assumptions ?? []).find((a) => a.slot === "scope");
  // everything the user asked for that this rule will NOT do — shown on the
  // card, not buried in prose, because it changes what the rule means
  const gaps: { request: string; why: string }[] = [];
  for (const g of [
    ...(turn.unmappable ?? []),
    ...turn.unsupported.map((u) => ({ request: u, why: "not supported yet" })),
  ]) {
    const key = g.request.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (!gaps.some((x) => x.request.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim() === key))
      gaps.push(g);
  }
  const fillKey = JSON.stringify(turn.rule ?? turn.draft); // re-trigger fill animation per turn
  // The WHOLE ask can be unmappable (e.g. "close the Hiver conversation
  // when the linked ClickUp task closes" -- a trigger this engine has no
  // vocabulary for at all) with NOTHING legal left over. A live test found
  // the WHEN/IF/THEN rows still rendering as blank "Hole" placeholders in
  // that case, implying there's a real rule skeleton to keep filling in
  // when there's nothing left to build -- misleading on top of the gaps
  // panel above, which already tells the whole story on its own.
  const nothingBuildable = gaps.length > 0 && !spec.trigger
    && spec.actions.length === 0 && groups.length === 0 && aiVars.length === 0;

  const copyJson = async () => {
    await navigator.clipboard.writeText(JSON.stringify(turn.rule, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-hairline bg-card">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
        <span className="font-mono text-[11px] font-semibold tracking-[0.18em] text-muted-foreground">
          AUTOMATION RULE
        </span>
        <span
          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${STATUS_STYLE[turn.status]}`}
        >
          {isLatest && applied
            ? "Applied ✓"
            : turn.done
              ? "Final — ready to build"
              : nothingBuildable
                ? "Not supported"
                : gaps.length
                  ? `Built with ${gaps.length} exclusion${gaps.length > 1 ? "s" : ""}`
                  : turn.status === "complete" && scopeAssumption
                    ? "Ready — 1 assumption"
                    : STATUS_LABEL[turn.status]}
        </span>
      </div>

      {gaps.length > 0 && (
        <div className="border-b border-hairline bg-destructive-soft px-4 py-2.5">
          <p className="text-[12px] font-semibold text-destructive">
            Left out of this rule — the rest was built:
          </p>
          <ul className="mt-1 space-y-0.5">
            {gaps.map((g, i) => (
              <li key={i} className="text-[12.5px] text-destructive">
                &ldquo;{g.request}&rdquo; — {g.why}
              </li>
            ))}
          </ul>
        </div>
      )}

      {turn.feature_request_offer && (
        <div className="border-b border-hairline bg-bone px-4 py-2.5">
          <p className="text-[12.5px] text-ink-soft">{turn.feature_request_offer}</p>
        </div>
      )}

      {!nothingBuildable && (
        <div key={fillKey} className="slot-filled px-4">
          <Row k="WHEN">
            {spec.trigger ? (
              // the builder's own label — the only vocabulary users can verify
              <span className="text-[13px] font-medium">
                {vocab?.triggers[spec.trigger] ?? spec.trigger}
              </span>
            ) : (
              <Hole hint="when should this run?" />
            )}
          </Row>

          {aiVars.length > 0 && (
            <Row k="AI">
              {aiVars.map((v) => (
                <span key={v.name} className="inline-flex flex-wrap items-baseline gap-1.5">
                  <Value>{v.name}</Value>
                  <span className="font-mono text-[11px] text-muted-foreground">{v.type}</span>
                  {v.options.length > 0 && (
                    <span className="text-[12px] text-muted-foreground">
                      one of {v.options.join(" / ")}
                    </span>
                  )}
                  <span className="text-[12px] text-ink-soft">— {v.description}</span>
                </span>
              ))}
            </Row>
          )}

          <Row k="IF">
            {groups.length ? (
              groups.map((g, gi) => (
                <span key={gi} className="inline-flex flex-wrap items-baseline gap-1.5">
                  {gi > 0 && (
                    <span className="font-mono text-[10px] font-semibold text-ink-soft">
                      AND
                    </span>
                  )}
                  {g.map((c, ci) => (
                    <span key={ci} className="inline-flex items-baseline gap-1.5">
                      {ci > 0 && (
                        <span className="font-mono text-[10px] font-semibold text-ink-soft">
                          OR
                        </span>
                      )}
                      <ConditionLine c={c} vocab={vocab} />
                    </span>
                  ))}
                </span>
              ))
            ) : spec.scope_confirmed ? (
              <span className="text-[13px] text-muted-foreground">
                no conditions — runs on every matching conversation, as you specified
              </span>
            ) : scopeAssumption ? (
              <ScopeAssumed
                onAnswer={onAnswer}
                disabled={disabled || !isLatest || applied}
              />
            ) : (
              <Hole hint="everything, or a subset?" />
            )}
          </Row>

          <Row k="THEN">
            {spec.actions.length ? (
              spec.actions.map((a, i) => (
                <span key={i} className="inline-flex flex-wrap items-baseline gap-1.5">
                  <span className="font-mono text-[11px] text-muted-foreground">{i + 1}.</span>
                  <ActionLine a={a} />
                </span>
              ))
            ) : (
              <Hole hint="what should happen?" />
            )}
          </Row>

          <Row k="ENABLED FOR">
            {spec.enabled_inboxes && spec.enabled_inboxes.length ? (
              <span className="text-[13px] font-medium">{spec.enabled_inboxes.join(", ")}</span>
            ) : (
              <Hole hint="which shared inbox(es)?" />
            )}
          </Row>

          {(turn.resolutions.filter((r) => r.value.toLowerCase() !== r.canonical.toLowerCase())
            .length > 0 ||
            turn.entity_notes.length > 0) && (
            <div className="my-4 flex flex-col gap-1.5 border-l-2 border-hairline pl-3">
              {turn.resolutions
                .filter((r) => r.value.toLowerCase() !== r.canonical.toLowerCase())
                .map((r, i) => (
                  <p key={i} className="text-[12px] text-ink-soft">
                    <span className="font-medium text-ink">matched</span>{" "}
                    &lsquo;{r.value}&rsquo; → {r.detail ?? r.canonical}
                  </p>
                ))}
              {turn.entity_notes.map((n, i) => (
                <p key={i} className="text-[12px] text-ink-soft">
                  {n}
                </p>
              ))}

            </div>
          )}
        </div>
      )}

      {turn.rule != null && (
        <div className="border-t border-hairline">
          {turn.test_run && <TestRunStrip testRun={turn.test_run} />}
          {isLatest && !applied && <PreviewStrip rule={turn.rule} />}
          {!isLatest ? null : applied ? (
            <div className="flex items-center justify-between bg-bone px-5 py-3">
              <span className="text-[13px] font-medium text-ink">
                Rule applied — recorded in the rule log.
              </span>
              <span className="text-[11px] text-ink-soft">
                (demo: stored locally, not built in Hiver)
              </span>
            </div>
          ) : confirming ? (
            <div className="flex items-center justify-between gap-3 bg-bone px-5 py-3">
              <span className="text-[13px] text-ink-soft">
                {scopeAssumption
                  ? `Create this rule? Creating confirms the assumption: it ${scopeAssumption.summary}.`
                  : "Create this rule? It runs on every matching conversation from then on."}
              </span>
              <span className="flex shrink-0 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirming(false)}
                >
                  Keep editing
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    setConfirming(false);
                    onApply();
                  }}
                >
                  Create rule
                </Button>
              </span>
            </div>
          ) : (
            <div className="flex items-center justify-between px-5 py-3">
              <span className="text-[12px] text-muted-foreground">
                {scopeAssumption
                  ? `Creating confirms: ${scopeAssumption.summary}.`
                  : "Review the structure above, then apply it."}
              </span>
              <Button onClick={() => setConfirming(true)}>Create this rule</Button>
            </div>
          )}
          <div className="flex items-center justify-between border-t border-hairline px-5 py-2.5">
            <button
              onClick={() => setShowJson((s) => !s)}
              className="font-mono text-[11px] font-semibold tracking-[0.14em] text-muted-foreground hover:text-ink"
            >
              {showJson ? "▾ MACHINE JSON" : "▸ MACHINE JSON"}
            </button>
            <Button variant="outline" size="sm" className="text-[11px]" onClick={copyJson}>
              {copied ? "Copied" : "Copy rule JSON"}
            </Button>
          </div>
          {showJson && (
            <pre className="max-h-56 overflow-auto border-t border-hairline bg-bone px-5 py-3 font-mono text-[11px] leading-relaxed text-ink-soft">
              {JSON.stringify(turn.rule, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
