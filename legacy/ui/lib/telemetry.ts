// ARCHIVED (2026-08-27, App Activation charter): the general Automations
// panel's own local telemetry — see legacy/ui/app/page.tsx's note. Kept
// for reference, not wired into the active build.
//
// Local accept / edit / abandon telemetry for generated rules — the prototype of
// the pilot's "session completion" and "generation quality" metrics. Stored in
// localStorage only; nothing leaves the browser.

export type RuleOutcome = "accepted" | "edited" | "abandoned";

export interface RuleLogEntry {
  id: string;
  ts: number;
  outcome: RuleOutcome;
  /** compact human summary: trigger · conditions · actions */
  summary: string;
  userTurns: number;
  rule: object | null;
}

const KEY = "copilot-rule-log";

export function loadLog(): RuleLogEntry[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function appendLog(entry: Omit<RuleLogEntry, "id" | "ts">): RuleLogEntry {
  const full: RuleLogEntry = {
    ...entry,
    id: Math.random().toString(36).slice(2, 10),
    ts: Date.now(),
  };
  const log = [full, ...loadLog()].slice(0, 200);
  window.localStorage.setItem(KEY, JSON.stringify(log));
  return full;
}

export function summarizeRule(rule: unknown): string {
  if (!rule || typeof rule !== "object") return "(no rule)";
  const r = rule as {
    trigger?: string;
    condition_groups?: unknown[][];
    actions?: { type?: string }[];
  };
  const conds = (r.condition_groups ?? []).reduce((n, g) => n + g.length, 0);
  const acts = (r.actions ?? []).map((a) => a.type).join(" + ") || "no actions";
  return `${r.trigger ?? "?"} · ${conds ? `${conds} condition${conds > 1 ? "s" : ""}` : "no conditions"} · ${acts}`;
}
