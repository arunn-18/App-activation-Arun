// Client for the copilot engine API (engine/serve_api.py in the v2 repo).
// Start it with:
//   cd <v2-repo>/engine && <venv-python> serve_api.py    -> http://127.0.0.1:8010

// Dev: .env.development points this at serve_api.py (port 8010, with SSE).
// Deployed: unset -> same-origin /api/* Python functions (no SSE; the stream
// client falls back to plain /api/chat automatically).
export const API_BASE = process.env.NEXT_PUBLIC_COPILOT_API ?? "";

export type Role = "user" | "assistant";
export interface ChatMessage {
  role: Role;
  content: string;
}

export interface Condition {
  property: string;
  op: string;
  values: string[];
  variable?: string | null;
}

export interface AiVariable {
  name: string;
  type: string;
  description: string;
  options: string[];
}

export interface Action {
  type: string;
  tags?: string[] | null;
  target?: string | null;
  targets?: string[] | null;
  status_value?: string | null;
  distribution?: string | null;
  content?: string | null;
  pinned?: boolean | null;
  email_enabled?: boolean | null;
  inbox?: string | null;
  body_hint?: string | null;
  /** connector action (v2.8): which recipe (engine/schema.py RECIPES) and the
   *  one setup-time slot that recipe needs — a real contact email to test-run
   *  the chain against before the rule is marked done. */
  recipe?: string | null;
  test_contact_email?: string | null;
}

export interface Spec {
  intent_summary: string;
  trigger: string | null;
  scope_confirmed: boolean;
  condition_groups: Condition[][];
  actions: Action[];
  ai_extract: { variables: AiVariable[] } | null;
  unsupported_requests: string[];
}

export interface Resolution {
  slot: string;
  value: string;
  canonical: string;
  detail?: string;
}

export interface QuestionOption {
  label: string;
  value: string;
}

export interface StructuredQuestion {
  slot: string;
  prompt: string;
  kind: "choice" | "text";
  options: QuestionOption[];
  multiple: boolean;
  allow_other: boolean;
  other_hint: string;
}

/** A reading the engine chose for the user on a slot where a legal rule exists
 *  either way (scope: run on everything). Not a blocking question — surfaced on
 *  the card and confirmed at apply time, or converted to "specified" by an
 *  answer in chat. */
export interface Assumption {
  slot: string;
  assumed: string;
  summary: string;
  question: string;
}

/** One step of a connector recipe's chain, as actually run (engine/executor.py
 *  run_chain()) — raw request/response, not a description of one. */
export interface ConnectorTestRunStep {
  kind: "api_call" | "assign";
  op?: string;
  args?: Record<string, unknown>;
  response?: { totalSize: number; done: boolean; records: Record<string, unknown>[] };
  target?: string;
}

/** Result of test-running a completed connector rule's recipe (v2.8) — the
 *  connector analogue of the preview dry-run every other rule gets: proof the
 *  rule does something real, before it's marked done. "no_match" is a clean,
 *  valid outcome (e.g. the test contact's account has no CSM), not an error. */
export interface ConnectorTestRun {
  status: "ok" | "no_match" | "error";
  steps: ConnectorTestRunStep[];
  variables: Record<string, unknown>;
  final: { type: "assign"; target: string } | null;
  reason?: string;
}

/** Track A result (engine/features.py): enabling an existing App feature.
 *  NOT an automation — no trigger, no conditions, no chain. */
export interface FeatureRequest {
  status: "complete" | "invalid";
  errors: string[];
  feature_id?: string;
  feature?: { id: string; app: string; name: string; description: string };
}

export interface TurnState {
  status: "complete" | "needs_info" | "invalid";
  /** "feature" when this turn resolved an app_feature ask (Track A) instead
   *  of building an automation rule — render a FeatureCard, not a RuleCard.
   *  Defaults to "automation" when absent (older engine payloads). */
  track?: "automation" | "feature";
  /** set only when track === "feature". */
  feature_request?: FeatureRequest | null;
  /** set only when the completed spec has a connector action — the real
   *  test-run result (engine/copilot.py connector_test_run), not present for
   *  any other rule type. */
  test_run?: ConnectorTestRun | null;
  /** schema-grounded answer when the user asked what the builder can do;
   *  the turn is read-only — the draft rule is unchanged */
  capability_answer?: string | null;
  /** requirements the rule vocabulary genuinely cannot express — declared,
   *  never approximated into a nearest-looking legal property */
  unmappable?: { request: string; why: string }[];
  /** the message carried no automation content (gibberish, small talk) — the
   *  turn is read-only and no rule card is worth showing */
  no_intent?: string | null;
  /** the latest user message was a wrap-up ("that's about it"), no new content */
  closing: boolean;
  /** closing AND the rule is complete: conversation is finished */
  done: boolean;
  intent_summary: string;
  spec: Spec;
  rule: object | null;
  draft: string;
  assumptions?: Assumption[];
  questions: string[];
  questions_structured?: StructuredQuestion[];
  questions_pending: number;
  errors: string[];
  unsupported: string[];
  hallucinated: string[];
  resolutions: Resolution[];
  entity_notes: string[];
}

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

/** Dry-run of a final rule over last week's mail (fixture in the demo; Hiver
 *  search in production) — blast radius before the rule exists. */
export interface RulePreview {
  previewable: boolean;
  reason?: string;
  window_days?: number;
  total?: number;
  matched?: number;
  sample?: { from: string; subject: string; received_at: string }[];
}

export async function fetchPreview(rule: object): Promise<RulePreview> {
  const res = await fetch(`${API_BASE}/api/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rule }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? `preview: HTTP ${res.status}`);
  return data as RulePreview;
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

/** True when this turn's questions render as a quick-answer form — i.e. whenever
 *  there are any. The questionnaire handles free-text items as well as choices,
 *  so gating on "has choices" only produced an inconsistency: a turn asking two
 *  text questions fell back to a prose list while a mixed turn got the form. */
export function hasQuestionForm(t: TurnState): boolean {
  return (
    !t.no_intent &&
    t.status === "needs_info" &&
    (t.questions_structured ?? []).length > 0
  );
}

/** A turn worth rendering a rule card for: something was actually built or
 *  asked about. Gibberish turns render as prose only. Track A turns (an
 *  app_feature ask) render a FeatureCard instead — see hasFeatureCard —
 *  never a RuleCard, since spec.trigger/actions are intentionally empty for
 *  those (Track A has no trigger, no actions; see engine/extract.py rule 20). */
export function hasRuleCard(t: TurnState): boolean {
  return (
    t.track !== "feature" &&
    (!t.no_intent || Boolean(t.spec.trigger) || t.spec.actions.length > 0)
  );
}

/** Track A: a turn worth rendering a FeatureCard for — an app_feature ask
 *  the engine resolved through features.py rather than the automation
 *  validator. */
export function hasFeatureCard(t: TurnState): boolean {
  return t.track === "feature" && t.feature_request != null;
}

// Compose the assistant reply from machine state. The rule card renders the
// structure; the prose carries understanding and what's needed next.
// `lead` prepends the intent restatement (Amplitude's "You want…" line) —
// used on the first turn and on the turn a rule first completes. When the
// questions render as a form, the prose doesn't repeat them.
export function assistantText(t: TurnState, lead = false): string {
  const parts: string[] = [];
  const intro = lead && t.intent_summary ? t.intent_summary : "";
  if (t.track === "feature" && t.feature_request) {
    // Track A: a completely different shape from an automation turn — no
    // WHEN/IF/THEN, no questions loop. The FeatureCard renders the detail;
    // this is just the lead-in line.
    const fr = t.feature_request;
    if (fr.status === "complete" && fr.feature)
      return `${fr.feature.name} is set up — review it below.`;
    return "This app feature isn't set up yet — see below for what's blocking it.";
  }
  if (t.no_intent) {
    // nothing to build from — say so instead of rendering a hollow draft
    parts.push(
      "I couldn't find an automation in that. Tell me what should happen and " +
        "when — for example \u201ctag emails from acme.com as VIP\u201d or " +
        "\u201cassign new incoming email to Dana\u201d."
    );
    if (t.spec.trigger || t.spec.actions.length)
      parts.push("Your draft is unchanged.");
    return parts.join("\n\n");
  }
  if (t.capability_answer) {
    // the question gets answered first; the rule state follows unchanged
    parts.push(t.capability_answer);
    if (t.status === "complete" && !t.done) {
      parts.push("Your draft is unchanged — adjust it or create it when ready.");
      return parts.join("\n\n");
    }
  }
  if (t.done) {
    return (
      "All set — the rule is final. Copy the JSON from the card, " +
      "or start a new automation for the next one."
    );
  }
  if (t.status === "complete") {
    parts.push(
      (intro ? intro + " " : "") + "Here's the rule — review it below."
    );
    if (t.entity_notes.length) parts.push(t.entity_notes.join(" "));
    parts.push("Want any adjustments?");
    return parts.join("\n\n");
  }
  if (intro) parts.push(intro);
  // ADDITIVE, never exclusive: an error must not suppress the questions and
  // notes computed alongside it. `invalid` used to return here, which hid the
  // fact that entities had been dropped from the rule.
  if (t.status === "invalid")
    parts.push(
      `I couldn't map part of that:\n${t.errors.map((e) => `• ${e}`).join("\n")}`
    );
  if (t.closing && t.questions.length)
    parts.push(
      "Sounds like that's everything from your side — but the rule can't run yet without a bit more:"
    );
  // only disclose scrubbed values the questions below don't already cover —
  // otherwise the same name is raised twice in one reply
  const covered = (v: string) =>
    t.questions.some((q) => q.toLowerCase().includes(v.toLowerCase()));
  const setAside = t.hallucinated.filter((v) => !covered(v));
  if (setAside.length)
    parts.push(
      `I set aside ${setAside.map((v) => `'${v}'`).join(", ")} — I couldn't confirm it from your message.`
    );
  if (t.entity_notes.length) parts.push(t.entity_notes.join(" "));
  if (hasQuestionForm(t)) {
    // the form renders the questions; the prose just hands off to it
    parts.push(
      t.questions.length > 1
        ? "A couple of quick questions to finish it:"
        : "One quick question to finish it:"
    );
    return parts.join("\n\n");
  }
  if (t.questions.length === 1) {
    parts.push(`To finish it: ${t.questions[0]}`);
  } else if (t.questions.length) {
    parts.push(
      `To finish it I need:\n${t.questions.map((q, i) => `${i + 1}. ${q}`).join("\n")}` +
        (t.questions_pending ? `\n(+${t.questions_pending} more after these.)` : "")
    );
  }
  return parts.join("\n\n") || "Tell me more about what should happen.";
}
