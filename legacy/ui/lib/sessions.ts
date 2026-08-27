// ARCHIVED (2026-08-27, App Activation charter): the general Automations
// panel's own session sidebar — see legacy/ui/app/page.tsx's note. Kept
// for reference, not wired into the active build.
//
// Chat sessions, Amplitude-style: a sidebar of past automations, persisted in
// localStorage. Each session carries its full transcript plus the per-turn
// machine state so inline rule cards re-render on revisit.

import type { ChatMessage, TurnState } from "./api";

export interface TurnWork {
  intent: string;
  steps: string[];
  turn?: TurnState;
}

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  work: Record<number, TurnWork>;
  applied: boolean;
  firstCompleteRule: string | null;
}

const KEY = "copilot-sessions";
const MAX_SESSIONS = 100;

export function newSession(): Session {
  return {
    id: Math.random().toString(36).slice(2, 10),
    title: "New automation",
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
    work: {},
    applied: false,
    firstCompleteRule: null,
  };
}

export function loadSessions(): Session[] {
  if (typeof window === "undefined") return [];
  try {
    const all = JSON.parse(window.localStorage.getItem(KEY) ?? "[]") as Session[];
    return all.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

export function saveSession(s: Session) {
  const rest = loadSessions().filter((x) => x.id !== s.id);
  window.localStorage.setItem(
    KEY,
    JSON.stringify([s, ...rest].slice(0, MAX_SESSIONS))
  );
}

export function sessionTitle(s: Session): string {
  const first = s.messages.find((m) => m.role === "user")?.content;
  return first ? (first.length > 60 ? first.slice(0, 57) + "…" : first) : "New automation";
}

export function groupLabel(ts: number): "Today" | "Previous 30 days" | "Older" {
  const d = new Date(ts);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) return "Today";
  if (Date.now() - ts < 30 * 24 * 3600 * 1000) return "Previous 30 days";
  return "Older";
}
