"use client";

import { useEffect, useRef, useState } from "react";
import FeatureCard from "@/components/FeatureCard";
import QuestionForm from "@/components/QuestionForm";
import RuleCard from "@/components/RuleCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  assistantText,
  fetchAppCatalog,
  fetchAppNames,
  hasFeatureCard,
  fetchTestableConversationsApp,
  hasQuestionForm,
  hasRuleCard,
  sendAppChat,
  testCreateFeatureApp,
  type AppCapability,
  type AppCatalog,
  type ChatMessage,
  type TurnState,
} from "@/lib/api";

/** The Apps panel: configuring ONE connected app's capabilities, and nothing
 *  else. Deliberately a SEPARATE page from the Automations copilot ("/") —
 *  that page's backend (serve_api.py) legitimately builds generic,
 *  non-app automations too (tag emails, assign to a teammate); this one
 *  talks to serve_apps.py, which only ever offers one app's Track A
 *  features, Track B recipes, and native actions. The suggestion chips
 *  below are pulled LIVE from that app's own catalog (GET /api/apps/<app>)
 *  — never a hardcoded example list — so there is no way for an unrelated
 *  automation idea to show up here as a "try one".
 */
export default function AppsPanel() {
  const [appNames, setAppNames] = useState<string[]>([]);
  const [selectedApp, setSelectedApp] = useState<string>("");
  const [catalog, setCatalog] = useState<AppCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [work, setWork] = useState<Record<number, TurnState>>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchAppNames()
      .then((names) => {
        setAppNames(names);
        setSelectedApp((cur) => cur || names[0] || "");
      })
      .catch(() =>
        setError(
          "Apps API is not reachable. Start it with: engine/serve_apps.py (port 8011)."
        )
      );
  }, []);

  useEffect(() => {
    if (!selectedApp) return;
    fetchAppCatalog(selectedApp).then(setCatalog).catch((e) =>
      setCatalogError(e instanceof Error ? e.message : String(e))
    );
  }, [selectedApp]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const switchApp = (app: string) => {
    if (app === selectedApp) return;
    setSelectedApp(app);
    setCatalog(null);
    setCatalogError(null);
    setMessages([]);
    setWork({});
    setApplied(false);
    setError(null);
  };

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy || !selectedApp) return;
    const next: ChatMessage[] = [...messages, { role: "user", content: trimmed }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const t = await sendAppChat(selectedApp, next);
      const lead = next.length === 1;
      setMessages([...next, { role: "assistant", content: assistantText(t, lead) }]);
      setWork((w) => ({ ...w, [next.length]: t }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMessages(messages); // roll back the user turn
      setInput(trimmed);
    } finally {
      setBusy(false);
    }
  };

  const latestTurnIndex = Object.keys(work)
    .map(Number)
    .sort((a, b) => b - a)[0];
  const currentTurn = latestTurnIndex != null ? work[latestTurnIndex] : undefined;

  const apply = () => setApplied(true);

  const isEmpty = messages.length === 0 && !busy;
  const suggestions = catalog ? buildSuggestions(catalog) : [];

  return (
    <main className="flex h-dvh">
      {/* catalog sidebar — the app switcher and its live capability list;
          this IS the "what's possible" answer, not prose the model made up */}
      <aside className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-hairline bg-card p-4">
        <p className="mb-2 text-[11px] font-semibold tracking-[0.18em] text-muted-foreground">
          APPS
        </p>
        <div className="mb-4 flex flex-wrap gap-1.5">
          {appNames.map((a) => (
            <button
              key={a}
              onClick={() => switchApp(a)}
              className={`rounded-full border px-3 py-1 text-[12.5px] transition-colors ${
                a === selectedApp
                  ? "border-ink bg-ink text-white"
                  : "border-hairline text-ink-soft hover:border-ink-soft"
              }`}
            >
              {capitalize(a)}
            </button>
          ))}
        </div>

        {catalogError && (
          <p className="mb-3 text-[12px] text-destructive">{catalogError}</p>
        )}

        {catalog && (
          <div className="space-y-5">
            <div>
              <Badge variant={catalog.connected ? "default" : "secondary"} className="text-[11px]">
                {catalog.connected ? "Connected" : "Not connected"}
              </Badge>
            </div>
            <CapabilitySection
              title="App features"
              items={catalog.track_a_features}
              onTry={send}
              disabled={busy}
            />
            <CapabilitySection
              title="Automation recipes"
              items={catalog.track_b_recipes}
              onTry={send}
              disabled={busy}
            />
            <CapabilitySection
              title="Native actions"
              items={catalog.native_actions}
              onTry={send}
              disabled={busy}
            />
          </div>
        )}
      </aside>

      {/* conversation, scoped to selectedApp only */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-hairline bg-card px-5 py-2.5">
          <span className="text-[13px] font-medium text-ink">
            {selectedApp ? `${capitalize(selectedApp)} setup` : "Apps"}
          </span>
          <Button variant="outline" size="sm" onClick={() => switchApp(selectedApp)}>
            Start over
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex min-h-full max-w-3xl flex-col px-6 pb-6 pt-8">
            {isEmpty && (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 pb-10">
                <h2 className="max-w-xl text-balance text-center text-[24px] font-semibold leading-tight tracking-tight">
                  {selectedApp
                    ? `What do you want to set up for ${capitalize(selectedApp)}?`
                    : "Loading apps…"}
                </h2>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    send(input);
                  }}
                  className="w-full max-w-xl"
                >
                  <div className="flex items-end gap-2 rounded-2xl border border-hairline bg-surface px-4 py-3 shadow-sm focus-within:border-ink-soft">
                    <textarea
                      rows={1}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          send(input);
                        }
                      }}
                      placeholder={`Describe what you want from ${capitalize(selectedApp || "the app")}`}
                      autoFocus
                      className="max-h-40 min-w-0 flex-1 resize-none bg-transparent py-1 text-[14px] leading-relaxed outline-none placeholder:text-muted-foreground"
                    />
                    <Button type="submit" size="sm" disabled={busy || !input.trim()}>
                      Send
                    </Button>
                  </div>
                </form>
                {suggestions.length > 0 && (
                  <div className="w-full max-w-xl space-y-2">
                    <p className="pb-1 text-center text-[12px] text-muted-foreground">
                      Or try one of this app&apos;s own capabilities:
                    </p>
                    {suggestions.map((s) => (
                      <button
                        key={s.prompt}
                        onClick={() => send(s.prompt)}
                        className="block w-full rounded-lg border border-hairline bg-card px-3.5 py-2.5 text-left text-[13px] text-ink-soft transition-colors hover:border-ink-soft hover:text-ink"
                      >
                        <span className="font-medium text-ink">{s.label}</span>
                        {s.blocked && (
                          <span className="ml-2 text-[11px] text-destructive">
                            blocked on: {s.blocked.join(", ")}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="space-y-4">
              {messages.map((m, i) => (
                <div key={i} className="space-y-3">
                  {m.role === "assistant" ? (
                    <div className="max-w-[92%] whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink">
                      {m.content}
                    </div>
                  ) : (
                    <div className="ml-auto w-fit max-w-[80%] whitespace-pre-wrap rounded-2xl bg-brand px-4 py-2 text-[13.5px] leading-relaxed text-white">
                      {m.content}
                    </div>
                  )}
                  {m.role === "assistant" && work[i] && hasFeatureCard(work[i]) && (
                    <FeatureCard
                      featureRequest={work[i].feature_request!}
                      onTestCreate={(fieldValues) =>
                        testCreateFeatureApp(
                          selectedApp,
                          work[i].feature_request!.feature_id!,
                          work[i].feature_request!.feature!,
                          fieldValues
                        )
                      }
                      fetchTestConversations={() =>
                        fetchTestableConversationsApp(selectedApp)
                      }
                    />
                  )}
                  {m.role === "assistant" && work[i] && hasRuleCard(work[i]) && (
                    <RuleCard
                      turn={work[i]}
                      isLatest={i === latestTurnIndex}
                      applied={applied}
                      onApply={apply}
                      onAnswer={send}
                      disabled={busy}
                    />
                  )}
                  {m.role === "assistant" &&
                    i === messages.length - 1 &&
                    work[i] &&
                    hasQuestionForm(work[i]) &&
                    !busy && (
                      <QuestionForm
                        questions={work[i].questions_structured!}
                        onAnswer={send}
                        disabled={busy}
                      />
                    )}
                </div>
              ))}
              {busy && (
                <p className="text-[12.5px] text-muted-foreground">Working…</p>
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

        {!isEmpty && (
          <div className="border-t border-hairline bg-card">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="mx-auto max-w-3xl px-6 pb-2 pt-3"
            >
              <div className="flex items-end gap-2 rounded-2xl border border-hairline bg-surface px-4 py-2.5 focus-within:border-ink-soft">
                <textarea
                  rows={1}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(input);
                    }
                  }}
                  placeholder={applied ? "Applied — start over for the next one" : "Answer or adjust…"}
                  disabled={applied}
                  autoFocus
                  className="max-h-40 min-w-0 flex-1 resize-none bg-transparent py-1 text-[13.5px] leading-relaxed outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
                />
                <Button type="submit" size="sm" disabled={busy || !input.trim() || applied}>
                  Send
                </Button>
              </div>
            </form>
          </div>
        )}
      </div>
    </main>
  );
}

function capitalize(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

/** The message sent when a suggestion chip is clicked. Just the capability's
 *  own name — e.g. "Create a Contact from Hiver", "Create a ClickUp task" —
 *  not a templated "Set up: X — Y" string. A live test found that template
 *  actively hurt classification: the router/extractor read "Set up: <name>
 *  — <description>" as too generic/automation-shaped, misrouting real
 *  Track A asks. Every catalog name here was already written to read as a
 *  plausible, natural thing a user might type — that's the whole reason to
 *  trust it verbatim instead of dressing it up. */
function suggestionPrompt(entry: AppCapability): string {
  return entry.name;
}

/** Every suggestion chip is derived straight from this app's own catalog —
 *  never a hand-picked example — so trying one can only ever mean trying a
 *  real App Integration capability, never an unrelated automation idea. */
function buildSuggestions(catalog: AppCatalog) {
  const all: { id: string; entry: AppCapability }[] = [
    ...Object.entries(catalog.track_a_features).map(([id, entry]) => ({ id, entry })),
    ...Object.entries(catalog.track_b_recipes).map(([id, entry]) => ({ id, entry })),
    ...Object.entries(catalog.native_actions).map(([id, entry]) => ({ id, entry })),
  ];
  return all.map(({ entry }) => ({
    label: entry.name,
    prompt: suggestionPrompt(entry),
    blocked: entry._blocked_on.length ? entry._blocked_on : null,
  }));
}

function CapabilitySection({
  title,
  items,
  onTry,
  disabled,
}: {
  title: string;
  items: Record<string, AppCapability>;
  onTry: (text: string) => void;
  disabled: boolean;
}) {
  const entries = Object.values(items);
  if (entries.length === 0) return null;
  return (
    <section>
      <p className="mb-2 text-[11px] font-medium text-muted-foreground">{title}</p>
      <div className="space-y-2">
        {entries.map((e) => (
          <button
            key={e.name}
            disabled={disabled}
            onClick={() => onTry(suggestionPrompt(e))}
            className="block w-full rounded-lg border border-hairline px-3 py-2 text-left transition-colors hover:border-ink-soft disabled:cursor-not-allowed disabled:opacity-60"
          >
            <p className="text-[12.5px] font-medium text-ink">{e.name}</p>
            <p className="mt-0.5 text-[11.5px] leading-snug text-ink-soft">
              {e.description}
            </p>
            {e._blocked_on.length > 0 && (
              <p className="mt-1 text-[11px] text-destructive">
                blocked on: {e._blocked_on.join(", ")}
              </p>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}
