// ARCHIVED (2026-08-27, App Activation charter): the general Automations
// panel's own API client — built ANY Hiver automation, with or without an
// app action, via engine/serve_api.py (now legacy/engine/serve_api.py).
// This engine is App Activation only now; ui/lib/api.ts is the active
// client, scoped entirely to the Apps panel (engine/serve_apps.py). Kept
// for reference, not wired into the active build — it imports shared
// types (ChatMessage, TurnState, FeatureRequest, TestCreateResult,
// TestableConversation) from "@/lib/api", which still export them.

import type {
  ChatMessage,
  FeatureRequest,
  TestableConversation,
  TestCreateResult,
  TurnState,
} from "@/lib/api";

// Dev: .env.development points this at serve_api.py (port 8010, with SSE).
// Deployed: unset -> same-origin /api/* Python functions (no SSE; the stream
// client falls back to plain /api/chat automatically).
export const API_BASE = process.env.NEXT_PUBLIC_COPILOT_API ?? "";

export interface Workspace {
  workspace: string;
  plan: string;
  shared_inboxes: { name: string; address: string }[];
  agents: { name: string; email: string }[];
  tags: string[];
}

export async function fetchWorkspace(): Promise<Workspace> {
  const res = await fetch(`${API_BASE}/api/workspace`);
  if (!res.ok) throw new Error(`workspace: HTTP ${res.status}`);
  return res.json();
}

/** Builder-vocabulary labels, served by the engine so they can't drift.
 *  Users can only verify a rule in the language the Hiver builder speaks. */
export interface Vocabulary {
  triggers: Record<string, string>;
  properties: Record<string, string>;
}

export async function fetchVocabulary(): Promise<Vocabulary> {
  const res = await fetch(`${API_BASE}/api/vocabulary`);
  if (!res.ok) throw new Error(`vocabulary: HTTP ${res.status}`);
  return res.json();
}

export async function sendChat(messages: ChatMessage[]): Promise<TurnState> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? `chat: HTTP ${res.status}`);
  return data as TurnState;
}

/** Automations page ("/"): POST /api/features/test-create. `feature` is the
 *  completed feature dict the client already has (FeatureRequest.feature)
 *  — the server has no independent memory of which fields were configured,
 *  same as every other turn in this engine trusting the client-echoed
 *  state. */
export async function testCreateFeatureAutomation(
  feature: NonNullable<FeatureRequest["feature"]>,
  fieldValues: Record<string, string>
): Promise<TestCreateResult> {
  const res = await fetch(`${API_BASE}/api/features/test-create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feature, field_values: fieldValues }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? `features/test-create: HTTP ${res.status}`);
  return data as TestCreateResult;
}

export async function fetchTestableConversationsAutomation(): Promise<TestableConversation[]> {
  const res = await fetch(`${API_BASE}/api/testable-conversations`);
  if (!res.ok) throw new Error(`testable-conversations: HTTP ${res.status}`);
  const data = await res.json();
  return data.conversations ?? [];
}

export interface ProgressEvent {
  type: "progress";
  stage: "extracting" | "lookup" | "validating";
  tool?: string;
  query?: string;
}

/** Human label for a real pipeline event. */
export function progressLabel(e: ProgressEvent): string {
  if (e.stage === "extracting") return "Reading your request";
  if (e.stage === "validating") return "Validating against the rule grammar";
  if (e.tool === "find_user")
    return e.query ? `Looking up '${e.query}' among teammates` : "Looking up teammates";
  if (e.tool === "list_tags") return "Checking the workspace tag list";
  if (e.tool === "list_inboxes") return "Checking shared inboxes";
  return "Consulting the workspace";
}

/** Final step label once the turn resolves. */
export function finalStepLabel(t: TurnState): string {
  if (t.status === "complete") return "Rule drafted";
  if (t.status === "invalid") return "Reporting what couldn't be mapped";
  return t.questions.length > 1
    ? `Planning questions (${t.questions.length})`
    : "Planning a question";
}

/** Streaming variant: real pipeline events via onProgress, resolves to the
 *  final TurnState. Falls back to the plain endpoint if streaming fails early. */
export async function sendChatStream(
  messages: ChatMessage[],
  onProgress: (e: ProgressEvent) => void
): Promise<TurnState> {
  const res = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok || !res.body) return sendChat(messages);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i).trim();
      buf = buf.slice(i + 2);
      if (!chunk.startsWith("data: ")) continue;
      const obj = JSON.parse(chunk.slice(6));
      if (obj.type === "progress") onProgress(obj as ProgressEvent);
      else if (obj.type === "result") return obj as TurnState;
      else if (obj.type === "error") throw new Error(obj.error);
    }
  }
  throw new Error("stream ended without a result");
}
