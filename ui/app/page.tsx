"use client";

import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import FeatureCard from "@/components/FeatureCard";
import QuestionForm from "@/components/QuestionForm";
import RuleCard from "@/components/RuleCard";
import StreamedText from "@/components/StreamedText";
import { WorkingLive, WorkingSummary } from "@/components/WorkingSteps";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  assistantText,
  fetchVocabulary,
  fetchWorkspace,
  finalStepLabel,
  hasFeatureCard,
  hasQuestionForm,
  hasRuleCard,
  progressLabel,
  sendChatStream,
  testCreateFeatureAutomation,
  type ChatMessage,
  type Vocabulary,
  type Workspace,
} from "@/lib/api";
import {
  groupLabel,
  loadSessions,
  newSession,
  saveSession,
  sessionTitle,
  type Session,
} from "@/lib/sessions";
import {
  appendLog,
  loadLog,
  summarizeRule,
  type RuleLogEntry,
} from "@/lib/telemetry";

// pilot scope is the non-AI surface; keep the demo prompts on it
const EXAMPLES = [
  "we get a lot of emails meant for jade, can you route them to her?",
  "assign every new incoming email to john",
  "auto-close everything that comes in from notifications@streamliner.example",
  "tag emails from acme.com appropriately",
  "assign new conversations to the account's CSM automatically, test with jordan@acme.example",
  "I want to see Salesforce account and contact details on conversations",
];

// one greeting per visit, Claude-style — all ask the same question differently
const GREETINGS = [
  "What should run on its own?",
  "What does the team do on repeat?",
  "Which emails shouldn't need a human?",
  "Describe it once. It runs forever.",
  "What do you tag, assign, or close every single day?",
  "What's the rule you keep enforcing by hand?",
];

const GROUPS = ["Today", "Previous 30 days", "Older"] as const;

export default function Playground() {
  const [session, setSession] = useState<Session>(() => newSession());
  const [history, setHistory] = useState<Session[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ws, setWs] = useState<Workspace | null>(null);
  const [vocab, setVocab] = useState<Vocabulary | undefined>(undefined);
  const [log, setLog] = useState<RuleLogEntry[]>([]);
  // real pipeline steps, live during the call
  const [liveSteps, setLiveSteps] = useState<string[] | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  // nothing said yet: greeting + composer own the centre, no docked input
  // picked client-side after mount so SSR and hydration agree
  const [greeting, setGreeting] = useState(GREETINGS[0]);
  // the assistant turn currently revealing; its rule card waits for the prose
  const [animateIdx, setAnimateIdx] = useState<number | null>(null);

  useEffect(() => {
    setGreeting(GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);
    setLog(loadLog());
    setHistory(loadSessions());
    fetchWorkspace()
      .then(setWs)
      .catch(() =>
        setError(
          "Engine API is not reachable. Start it with: engine/serve_api.py (port 8010)."
        )
      );
    fetchVocabulary().then(setVocab).catch(() => undefined); // ids render as fallback
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session.messages, liveSteps]);

  const persist = (s: Session) => {
    setSession(s);
    if (s.messages.length) {
      saveSession(s);
      setHistory(loadSessions());
    }
  };

  // the latest assistant turn that carries machine state
  const latestTurnIndex = Object.keys(session.work)
    .map(Number)
    .filter((i) => session.work[i].turn)
    .sort((a, b) => b - a)[0];

  const currentTurn =
    latestTurnIndex != null ? session.work[latestTurnIndex]?.turn : undefined;

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    const next: ChatMessage[] = [
      ...session.messages,
      { role: "user", content: trimmed },
    ];
    const pending: Session = { ...session, messages: next, updatedAt: Date.now() };
    pending.title = sessionTitle(pending);
    persist(pending);
    setInput("");
    setBusy(true);
    setError(null);
    setLiveSteps([]);
    const steps: string[] = [];
    try {
      const t = await sendChatStream(next, (e) => {
        steps.push(progressLabel(e));
        setLiveSteps([...steps]);
      });
      steps.push(finalStepLabel(t));
      // lead with the intent restatement on the first turn and on the turn a
      // rule first completes (Amplitude's "You want…" line)
      const lead =
        next.length === 1 || (!pending.firstCompleteRule && !!t.rule);
      const s2: Session = {
        ...pending,
        messages: [...next, { role: "assistant", content: assistantText(t, lead) }],
        work: {
          ...pending.work,
          [next.length]: { intent: t.intent_summary, steps, turn: t },
        },
        firstCompleteRule:
          pending.firstCompleteRule ?? (t.rule ? JSON.stringify(t.rule) : null),
        updatedAt: Date.now(),
      };
      persist(s2);
      setAnimateIdx(next.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      persist({ ...session, updatedAt: Date.now() }); // roll back the user turn
      setInput(trimmed);
    } finally {
      setBusy(false);
      setLiveSteps(null);
    }
  };

  const apply = () => {
    if (!currentTurn?.rule) return;
    const edited =
      session.firstCompleteRule !== null &&
      JSON.stringify(currentTurn.rule) !== session.firstCompleteRule;
    appendLog({
      outcome: edited ? "edited" : "accepted",
      summary: summarizeRule(currentTurn.rule),
      userTurns: session.messages.filter((m) => m.role === "user").length,
      rule: currentTurn.rule,
    });
    setLog(loadLog());
    persist({
      ...session,
      applied: true,
      messages: [
        ...session.messages,
        {
          role: "assistant",
          content:
            "Rule created and recorded in the rule log (demo — stored locally, not built in Hiver). Start a new automation for the next one.",
        },
      ],
      updatedAt: Date.now(),
    });
  };

  const startNew = () => {
    // a completed rule left unapplied when moving on counts as abandoned —
    // the metric that shows when the copilot builds rules people don't apply
    if (currentTurn?.rule && !session.applied) {
      appendLog({
        outcome: "abandoned",
        summary: summarizeRule(currentTurn.rule),
        userTurns: session.messages.filter((m) => m.role === "user").length,
        rule: currentTurn.rule,
      });
      setLog(loadLog());
    }
    setSession(newSession());
    setError(null);
    setInput("");
  };

  const isEmpty = session.messages.length === 0 && !busy;

  const grouped = GROUPS.map((g) => ({
    label: g,
    items: history.filter((s) => groupLabel(s.updatedAt) === g),
  })).filter((g) => g.items.length);

  return (
    <main className="flex h-dvh">
      {/* sidebar: new automation + history */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-hairline bg-card">
        <div className="p-3">
          <Button className="w-full justify-start gap-2" onClick={startNew}>
            <Plus className="size-4" />
            New automation
          </Button>
        </div>
        <div className="min-h-0 flex-1 scroll-fade overflow-y-auto px-3 pb-4">
          {grouped.length === 0 && (
            <p className="px-2 pt-2 text-[12px] text-muted-foreground">
              Past automations appear here.
            </p>
          )}
          {grouped.map((g) => (
            <div key={g.label} className="mb-3">
              <p className="px-2 py-1.5 text-[11px] font-medium text-muted-foreground">
                {g.label}
              </p>
              {g.items.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    setSession(s);
                    setError(null);
                    setInput("");
                    setAnimateIdx(null);
                  }}
                  className={`block w-full truncate rounded-md px-2 py-1.5 text-left text-[13px] transition-colors ${
                    s.id === session.id
                      ? "bg-bone font-medium text-ink"
                      : "text-ink-soft hover:bg-bone"
                  }`}
                >
                  {s.title}
                </button>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {/* main column */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* floats over the scroll so content blurs through it */}
        <header className="absolute inset-x-0 top-0 z-10 flex items-center justify-end border-b border-hairline bg-card/70 px-5 py-2.5 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2 text-[12px]">
                  <span
                    className={`size-1.5 rounded-full ${ws ? "bg-ink" : "bg-destructive"}`}
                  />
                  {ws ? "Workspace" : "Engine offline"}
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-96 overflow-y-auto">
                <SheetHeader>
                  <SheetTitle className="text-[14px]">
                    {ws?.workspace ?? "No workspace"}
                  </SheetTitle>
                  <SheetDescription className="text-[12px]">
                    What the entity resolver knows about. Names you use get
                    matched against these; nothing outside them is ever invented.
                  </SheetDescription>
                </SheetHeader>
                {ws && (
                  <div className="space-y-5 px-4 pb-6">
                    <section>
                      <p className="mb-2 text-[11px] font-medium text-muted-foreground">
                        Tags
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {ws.tags.map((t) => (
                          <Badge
                            key={t}
                            variant="secondary"
                            className="font-mono text-[11px]"
                          >
                            {t}
                          </Badge>
                        ))}
                      </div>
                    </section>
                    <section>
                      <p className="mb-2 text-[11px] font-medium text-muted-foreground">
                        Agents
                      </p>
                      {ws.agents.map((a) => (
                        <p key={a.email} className="py-0.5 text-[13px]">
                          {a.name}{" "}
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {a.email}
                          </span>
                        </p>
                      ))}
                    </section>
                    <section>
                      <p className="mb-2 text-[11px] font-medium text-muted-foreground">
                        Shared inboxes
                      </p>
                      {ws.shared_inboxes.map((i) => (
                        <p key={i.address} className="py-0.5 text-[13px]">
                          {i.name}{" "}
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {i.address}
                          </span>
                        </p>
                      ))}
                    </section>
                  </div>
                )}
              </SheetContent>
            </Sheet>

            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="text-[12px]">
                  Rule log ({log.length})
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-[30rem] overflow-y-auto">
                <SheetHeader>
                  <SheetTitle className="text-[14px]">Rule log</SheetTitle>
                  <SheetDescription className="text-[12px]">
                    Every applied or abandoned rule, with its outcome. Accepted =
                    applied as generated; edited = adjusted after first
                    completion; abandoned = completed but never applied. Stored
                    locally (demo).
                  </SheetDescription>
                </SheetHeader>
                <div className="px-4 pb-6">
                  {log.length === 0 ? (
                    <p className="text-[12px] text-muted-foreground">
                      No rules yet. Apply one and it lands here.
                    </p>
                  ) : (
                    log.map((e) => (
                      <div
                        key={e.id}
                        className="flex items-baseline gap-3 border-b border-hairline py-2 text-[12px] last:border-b-0"
                      >
                        <span
                          className={`w-20 shrink-0 rounded-sm px-1.5 py-0.5 text-center font-mono text-[10px] font-semibold ${
                            e.outcome === "accepted"
                              ? "bg-bone text-ink"
                              : e.outcome === "edited"
                                ? "bg-bone text-ink-soft"
                                : "bg-destructive-soft text-destructive"
                          }`}
                        >
                          {e.outcome.toUpperCase()}
                        </span>
                        <span className="min-w-0 flex-1 font-mono text-[11px] leading-relaxed text-ink-soft">
                          {e.summary}
                        </span>
                        <span className="shrink-0 text-muted-foreground">
                          {e.userTurns}t · {new Date(e.ts).toLocaleTimeString()}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </header>

        {/* centered conversation */}
        <div className="min-h-0 flex-1 scroll-fade overflow-y-auto">
          <div className="mx-auto flex min-h-full max-w-3xl flex-col px-6 pb-6 pt-16">
            {isEmpty && (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-7 pb-10">
                {/* greeting and composer travel together, centred — the page
                    has nothing else on it, so a bottom-docked input reads as
                    stranded */}
                {/* text-balance evens the lines so the last word never drops
                    alone; width matches the composer below it */}
                <h2 className="max-w-2xl text-balance text-center text-[26px] font-semibold leading-tight tracking-tight">
                  {greeting}
                </h2>

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    send(input);
                    if (composerRef.current)
                      composerRef.current.style.height = "auto";
                  }}
                  className="w-full max-w-2xl"
                >
                  <div className="flex items-end gap-2 rounded-2xl border border-hairline bg-surface px-4 py-3 shadow-sm transition-colors focus-within:border-ink-soft">
                    <textarea
                      ref={composerRef}
                      rows={1}
                      value={input}
                      onChange={(e) => {
                        setInput(e.target.value);
                        e.currentTarget.style.height = "auto";
                        e.currentTarget.style.height =
                          Math.min(e.currentTarget.scrollHeight, 160) + "px";
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          send(input);
                          e.currentTarget.style.height = "auto";
                        }
                      }}
                      placeholder="Describe the automation in plain English"
                      autoFocus
                      className="max-h-40 min-w-0 flex-1 resize-none bg-transparent py-1 text-[14px] leading-relaxed outline-none placeholder:text-muted-foreground"
                    />
                    <Button type="submit" size="sm" disabled={busy || !input.trim()}>
                      Send
                    </Button>
                  </div>
                </form>

                <div className="mx-auto w-full max-w-2xl space-y-2">
                  <p className="pb-1 text-center text-[12px] text-muted-foreground">
                    Or try one:
                  </p>
                  {EXAMPLES.map((e) => (
                    <button
                      key={e}
                      onClick={() => send(e)}
                      className="block w-full rounded-lg border border-hairline bg-card px-3.5 py-2.5 text-left text-[13px] text-ink-soft transition-colors hover:border-ink-soft hover:text-ink"
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-4">
              {session.messages.map((m, i) => (
                // keyed by session too: an expanded working-summary must not
                // leak its open state onto another session's turn at the same
                // index when switching in the sidebar
                <div key={`${session.id}-${i}`} className="space-y-3">
                  {m.role === "assistant" && session.work[i] && (
                    <WorkingSummary steps={session.work[i].steps} />
                  )}
                  {m.role === "assistant" ? (
                    <StreamedText
                      text={m.content}
                      animate={i === animateIdx}
                      onDone={() => setAnimateIdx(null)}
                      className="max-w-[92%] whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink"
                    />
                  ) : (
                    <div className="ml-auto w-fit max-w-[80%] whitespace-pre-wrap rounded-2xl bg-brand px-4 py-2 text-[13.5px] leading-relaxed text-white">
                      {m.content}
                    </div>
                  )}
                  {m.role === "assistant" &&
                    i !== animateIdx &&
                    session.work[i]?.turn &&
                    hasFeatureCard(session.work[i].turn!) && (
                    <FeatureCard
                      featureRequest={session.work[i].turn!.feature_request!}
                      onTestCreate={(fieldValues) =>
                        testCreateFeatureAutomation(
                          session.work[i].turn!.feature_request!.feature!,
                          fieldValues
                        )
                      }
                    />
                  )}
                  {m.role === "assistant" &&
                    i !== animateIdx &&
                    session.work[i]?.turn &&
                    hasRuleCard(session.work[i].turn!) && (
                    <RuleCard
                      turn={session.work[i].turn!}
                      isLatest={i === latestTurnIndex}
                      applied={session.applied}
                      onApply={apply}
                      vocab={vocab}
                      onAnswer={send}
                      disabled={busy}
                    />
                  )}
                  {m.role === "assistant" &&
                    i === session.messages.length - 1 &&
                    i !== animateIdx &&
                    session.work[i]?.turn &&
                    hasQuestionForm(session.work[i].turn!) &&
                    !busy && (
                      <QuestionForm
                        questions={session.work[i].turn!.questions_structured!}
                        onAnswer={send}
                        disabled={busy}
                      />
                    )}
                </div>
              ))}
              {busy && liveSteps && (
                <WorkingLive
                  steps={liveSteps.length ? liveSteps : ["Reading your request"]}
                />
              )}
              {error && (
                <div className="rounded-lg border border-destructive bg-destructive-soft px-3 py-2 text-[12px] text-destructive">
                  {error}
                </div>
              )}
              <div ref={endRef} />
            </div>
          </div>
        </div>

        {/* docked composer — only once the conversation has started; on the
            empty state it sits centred under the greeting instead */}
        {!isEmpty && (
        <div className="border-t border-hairline bg-card">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
              if (composerRef.current) composerRef.current.style.height = "auto";
            }}
            className="mx-auto max-w-3xl px-6 pb-2 pt-3"
          >
            <div className="flex items-end gap-2 rounded-2xl border border-hairline bg-surface px-4 py-2.5 transition-colors focus-within:border-ink-soft">
              <textarea
                ref={composerRef}
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  e.currentTarget.style.height = "auto";
                  e.currentTarget.style.height =
                    Math.min(e.currentTarget.scrollHeight, 160) + "px";
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                    e.currentTarget.style.height = "auto";
                  }
                }}
                placeholder={
                  session.applied
                    ? "Rule applied — start a new automation"
                    : session.messages.length
                      ? "Answer or adjust…"
                      : "e.g. tag every invoice email"
                }
                disabled={session.applied}
                autoFocus
                className="max-h-40 min-w-0 flex-1 resize-none bg-transparent py-1 text-[13.5px] leading-relaxed outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
              />
              <Button
                type="submit"
                size="sm"
                disabled={busy || !input.trim() || session.applied}
              >
                Send
              </Button>
            </div>
          </form>
        </div>
        )}

        {/* always visible, whichever state we're in — testers need the
            boundary in front of them, not only on first load */}
        <p className="px-6 pb-3 pt-2 text-center text-[11px] leading-relaxed text-muted-foreground">
          One app automation supported so far — Salesforce auto-assign to the
          account&rsquo;s CSM. Not covered yet — AI detection or extraction,
          other app integrations (other Salesforce actions, HubSpot&hellip;),
          and Time Passed Since / Date / Day conditions. Rules are drafts;
          nothing is built in Hiver.
        </p>
      </div>
    </main>
  );
}
