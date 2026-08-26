// Client for the copilot engine API (engine/serve_api.py in the v2 repo).
// Start it with:
//   cd <v2-repo>/engine && <venv-python> serve_api.py    -> http://127.0.0.1:8010

// Dev: .env.development points this at serve_api.py (port 8010, with SSE).
// Deployed: unset -> same-origin /api/* Python functions (no SSE; the stream
// client falls back to plain /api/chat automatically).
export const API_BASE = process.env.NEXT_PUBLIC_COPILOT_API ?? "";

// The Apps panel (ui/app/apps/page.tsx) talks to a DIFFERENT server —
// engine/serve_apps.py, scoped by app, not the general Automations
// copilot's serve_api.py — so it needs its own base URL, not API_BASE.
// Start it with:
//   cd <v2-repo>/engine && <venv-python> serve_apps.py    -> http://127.0.0.1:8011
export const APPS_API_BASE = process.env.NEXT_PUBLIC_APPS_API ?? "";

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
  /** A native app-action automation (v2.12, capability 5) — Hiver's own
   *  pre-built action block (e.g. "Create tasks automatically via
   *  automation"), NOT an API call
   *  this engine composes. target_name (which list/board/channel) and
   *  title_hint (what it should be titled/about) are its two generic slots
   *  (engine/schema.py's NATIVE_ACTIONS). Mutually exclusive with
   *  `recipe`/`custom_plan` — exactly one of the three connector mechanisms
   *  is ever set. */
  native_action_id?: string | null;
  target_name?: string | null;
  title_hint?: string | null;
  /** A dynamically-composed connector plan (v2.11) — the OTHER way to fill a
   *  connector action when no RECIPES entry or native action matches: the
   *  engine composed its own lookup chain from the Salesforce object/field
   *  catalog instead of following a fixed recipe. */
  custom_plan?: ConnectorPlan | null;
  /** Derived, read-only: the recipe's or plan's own terminal chain step,
   *  surfaced generically so the draft/final JSON show what the connector
   *  actually does end to end (look up data, then act on it), not just that
   *  it ran. Exactly one of the two is set, matching the terminal kind. */
  assigns_to?: string | null;
  tags_with?: string | null;
}

/** One lookup step of a dynamically-composed connector plan (v2.11) — see
 *  automation/plan_validator.py. `eq` values may carry a {{variable}} ref to
 *  an earlier step's own extract_variables entry. */
export interface ConnectorPlanStep {
  object: string;
  where: { field: string; eq: string }[];
  extract_variables: { variable: string; field: string }[];
}

export interface ConnectorPlanTerminal {
  kind: "assign" | "add_tag";
  target: string | null;
  tags: string[] | null;
}

export interface ConnectorPlan {
  app: string;
  plan_summary: string;
  steps: ConnectorPlanStep[];
  terminal: ConnectorPlanTerminal;
}

export interface Spec {
  intent_summary: string;
  trigger: string | null;
  scope_confirmed: boolean;
  condition_groups: Condition[][];
  actions: Action[];
  ai_extract: { variables: AiVariable[] } | null;
  unsupported_requests: string[];
  /** which shared inbox(es) this RULE is enabled for — a property of the
   *  whole rule, not one action (engine/automation/validator.py). Empty
   *  until named; required (when a workspace is loaded) before the rule can
   *  reach "complete", the same way a Track A feature needs inboxes too. */
  enabled_inboxes?: string[];
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

/** One input inside a "form"-kind StructuredQuestion (capability 5's "one
 *  block" native-action field form — engine/automation/validator.py's
 *  _native_action_form). `value` pre-fills whatever's already known;
 *  `options` is present only when `kind === "choice"` (e.g. priority). */
export interface FormField {
  key: string;
  label: string;
  required: boolean;
  value: string;
  kind?: "choice";
  options?: QuestionOption[];
}

export interface StructuredQuestion {
  slot: string;
  prompt: string;
  kind: "choice" | "text" | "form";
  options: QuestionOption[];
  multiple: boolean;
  allow_other: boolean;
  other_hint: string;
  /** set only when kind === "form" — every field to collect together in
   *  one block, instead of one sequential question per field. */
  fields?: FormField[];
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

/** One step of a connector recipe's (or dynamic plan's) chain, as actually
 *  run (engine/executor.py run_chain()) — raw request/response, not a
 *  description of one. */
export interface ConnectorTestRunStep {
  kind: "api_call" | "assign" | "add_tag";
  op?: string;
  args?: Record<string, unknown>;
  response?: { totalSize: number; done: boolean; records: Record<string, unknown>[] };
  target?: string;
  tags?: string[];
}

/** Result of test-running a completed connector rule's recipe or dynamic
 *  plan (v2.8, v2.11) — the connector analogue of the preview dry-run every
 *  other rule gets: proof the rule does something real, before it's marked
 *  done. "no_match" is a clean, valid outcome for a fixed recipe (e.g. the
 *  test contact's account has no CSM) — NOT for a dynamic plan, which the
 *  engine requires to actually succeed before it ever reaches this
 *  "complete" state at all (see automation/validator.py's connector block). */
export interface ConnectorTestRun {
  status: "ok" | "no_match" | "error";
  steps: ConnectorTestRunStep[];
  variables: Record<string, unknown>;
  final: { type: "assign"; target: string } | { type: "add_tag"; tags: string[] } | null;
  reason?: string;
}

/** Result of firing a native app action for real (v2.12, capability 5) — the
 *  native-action analogue of ConnectorTestRun above, for a mechanism with no
 *  chain: it either ran or it didn't (no "no_match", no per-step log,
 *  distinguished from ConnectorTestRun by having a `result` key instead of
 *  `steps`/`final` — see engine/automation/executor.py's run_native_action). */
export interface NativeActionTestRun {
  status: "ok" | "error";
  result: Record<string, unknown> | null;
  reason?: string;
}

/** Track A result (engine/features.resolve_setup()): a multi-turn guided
 *  setup for an existing App feature — Authentication -> pick records ->
 *  pick fields per record (from a live "describe" call) -> enable for the
 *  shared inbox(es) it applies to (naming inbox(es) IS the enable action,
 *  not a separate plain yes/no CTA). NOT an automation — no trigger, no
 *  conditions, no chain. `status` mirrors TurnState.status ("needs_info"
 *  mid-setup); questions/questions_structured drive the SAME QuestionForm
 *  the automation flow uses. */
export interface FeatureRequest {
  status: "complete" | "needs_info" | "invalid";
  errors: string[];
  /** also carried at the top level (TurnState.questions/questions_structured)
   *  — QuestionForm reads those; this copy is what assistantText's lead-in
   *  line quotes. */
  questions: string[];
  feature_id?: string;
  feature?: {
    id: string; app: string; name: string; description: string;
    objects: string[]; fields_by_object: Record<string, string[]>;
    inboxes: string[];
    /** "view" (default) shows existing data; "write" creates a NEW record —
     *  decides preview vs. the write-test-create form below. */
    kind?: "view" | "write";
  };
  /** what's been resolved so far, for a running summary — same spirit as
   *  RuleCard showing partial WHEN/IF/THEN while slots are still open. */
  progress?: {
    connected?: boolean;
    objects?: string[];
    fields_by_object?: Record<string, string[]>;
    inboxes?: string[];
  };
  /** "test on a real conversation" (v2.13, capability 7) — set only once
   *  the admin names a real contact/conversation to preview against
   *  (engine/apps/setup.py's preview_feature()); a courtesy, never required
   *  to reach status "complete". "no_match" is a clean, honest outcome
   *  (that contact doesn't exist in Salesforce) — not an error. */
  preview?:
    | { status: "ok"; contact_email: string;
        values_by_object: Record<string, Record<string, unknown>> }
    | { status: "no_match"; contact_email: string; reason: string }
    | null;
}

export interface TurnState {
  status: "complete" | "needs_info" | "invalid";
  /** "feature" when this turn resolved an app_feature ask (Track A) instead
   *  of building an automation rule — render a FeatureCard, not a RuleCard.
   *  Defaults to "automation" when absent (older engine payloads). */
  track?: "automation" | "feature";
  /** set only when track === "feature". */
  feature_request?: FeatureRequest | null;
  /** "test on a real conversation" (capability 7) nudge for Track A: set
   *  only once the feature is fully enabled (feature_request.status ===
   *  "complete") AND nobody has named a contact to preview it against yet
   *  (feature_request.preview is absent) — a courtesy pointer at real
   *  mailbox conversations, never shown once a preview has actually run. */
  feature_test_suggestion?: string | null;
  /** set only when the completed spec has a connector action — the real
   *  test-run result (engine/copilot.py connector_test_run), not present for
   *  any other rule type. A native-action connector (capability 5) returns
   *  NativeActionTestRun's shape instead — check for a `result` key to tell
   *  them apart, same as copilot.py's own _render_test_run does. */
  test_run?: ConnectorTestRun | NativeActionTestRun | null;
  /** schema-grounded answer when the user asked what the builder can do;
   *  the turn is read-only — the draft rule is unchanged */
  capability_answer?: string | null;
  /** structured, clickable capabilities the SAME question is actually
   *  about (engine/docent.py's relevant_capabilities()) — [] whenever the
   *  topic doesn't name discrete capabilities (e.g. "how does assignment
   *  work?" has no single badge-able entry) or there's no capability
   *  question this turn. Always [] alongside a null capability_answer. */
  capability_badges?: { id: string; name: string; app: string;
                        kind: "app_feature" | "recipe" | "native_action" }[];
  /** requirements the rule vocabulary genuinely cannot express — declared,
   *  never approximated into a nearest-looking legal property */
  unmappable?: { request: string; why: string }[];
  /** the message carried no automation content (gibberish, small talk) — the
   *  turn is read-only and no rule card is worth showing */
  no_intent?: string | null;
  /** "you want X, I can do that via Y — here's how" — set ONLY on the turn a
   *  capability (Track A feature, or a Track B recipe/native action/composed
   *  plan) is first matched, composed entirely from that capability's own
   *  name/description (engine/copilot.py's _mapping_explanation). null on
   *  every later turn of the same conversation and whenever nothing has
   *  been matched yet. */
  mapping_explanation?: string | null;
  /** Discovery movement's "log this as a feature request?" courtesy
   *  (Apps Activation PRD, 2026-08-24) — set only when this turn has an
   *  `unmappable` item: the offer question text (not yet answered), a
   *  decline acknowledgment, or a logged confirmation, depending on
   *  spec.feature_request_requested. null whenever nothing is unmappable. */
  feature_request_offer?: string | null;
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

// ---- Apps panel (engine/serve_apps.py) ------------------------------------
// Scoped to ONE app at a time — Track A features, Track B recipes, and
// native actions for that app ONLY. No generic (non-app) automation surface
// exists here; that's the Automations copilot above, a deliberately
// different product surface.

/** One capability entry from GET /api/apps/<app> — a Track A feature, a
 *  Track B recipe, or a native action, all the same shape from the UI's
 *  point of view: something to show, and whether it's blocked right now. */
export interface AppCapability {
  app: string;
  name: string;
  description: string;
  prerequisites: string[];
  /** unmet prerequisite keys — empty means buildable right now. */
  _blocked_on: string[];
  kind?: "view" | "write"; // Track A features only
}

export interface AppCatalog {
  app: string;
  connected: boolean;
  track_a_features: Record<string, AppCapability>;
  track_b_recipes: Record<string, AppCapability>;
  native_actions: Record<string, AppCapability>;
}

export async function fetchAppNames(): Promise<string[]> {
  const res = await fetch(`${APPS_API_BASE}/api/apps`);
  if (!res.ok) throw new Error(`apps: HTTP ${res.status}`);
  const data = await res.json();
  return data.apps ?? [];
}

export async function fetchAppCatalog(app: string): Promise<AppCatalog> {
  const res = await fetch(`${APPS_API_BASE}/api/apps/${encodeURIComponent(app)}`);
  if (!res.ok) throw new Error(`apps/${app}: HTTP ${res.status}`);
  return res.json();
}

/** Apps-panel chat — scoped to one app, no SSE (serve_apps.py's /chat is a
 *  single synchronous call, unlike serve_api.py's /chat/stream). Returns the
 *  SAME TurnState shape respond_structured() always has, so FeatureCard,
 *  RuleCard, and QuestionForm all work unmodified against it. */
export async function sendAppChat(
  app: string,
  messages: ChatMessage[]
): Promise<TurnState> {
  const res = await fetch(`${APPS_API_BASE}/api/apps/${encodeURIComponent(app)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error ?? `apps/${app}/chat: HTTP ${res.status}`);
  return data as TurnState;
}

/** capability 7 for a WRITE Track A feature — the result of actually
 *  creating a mock record (engine/copilot.test_create_feature). "error"
 *  covers both a rejected submission (an unexposed field) and a server-
 *  side prerequisite recheck failing — never silently ignored either way. */
export interface TestCreateResult {
  status: "ok" | "error";
  object?: string;
  record?: Record<string, unknown>;
  reason?: string;
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

/** Apps panel ("/apps"): POST /api/apps/<app>/features/<feature_id>/test-create. */
export async function testCreateFeatureApp(
  app: string,
  featureId: string,
  feature: NonNullable<FeatureRequest["feature"]>,
  fieldValues: Record<string, string>
): Promise<TestCreateResult> {
  const res = await fetch(
    `${APPS_API_BASE}/api/apps/${encodeURIComponent(app)}/features/` +
      `${encodeURIComponent(featureId)}/test-create`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature, field_values: fieldValues }),
    }
  );
  const data = await res.json();
  if (!res.ok)
    throw new Error(data?.error ?? `apps/${app}/features/${featureId}/test-create: HTTP ${res.status}`);
  return data as TestCreateResult;
}

/** capability 7's conversation picker (mailbox_lookup.testable_
 *  conversations) — REAL mailbox conversations, most recent first, whose
 *  sender is a known contact in the app's fixture. Shown BEFORE a write
 *  feature's create-form (or used to preview a view feature) — never
 *  skipped past straight into the form. */
export interface TestableConversation {
  id: string;
  from: string;
  subject: string;
  received_at: string;
}

export async function fetchTestableConversationsAutomation(): Promise<TestableConversation[]> {
  const res = await fetch(`${API_BASE}/api/testable-conversations`);
  if (!res.ok) throw new Error(`testable-conversations: HTTP ${res.status}`);
  const data = await res.json();
  return data.conversations ?? [];
}

export async function fetchTestableConversationsApp(app: string): Promise<TestableConversation[]> {
  const res = await fetch(
    `${APPS_API_BASE}/api/apps/${encodeURIComponent(app)}/testable-conversations`
  );
  if (!res.ok) throw new Error(`apps/${app}/testable-conversations: HTTP ${res.status}`);
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
 *  those (Track A has no trigger, no actions; see engine/extract.py rule 20).
 *
 *  Also prose-only for a BARE capability question that built nothing — a
 *  live test found this rendering a misleading RuleCard with an "excluded"
 *  question in it, for a turn that was really just a question docent.py
 *  already answered in full. Gated on `actions` alone, NOT `trigger` —
 *  automation/extract.py's own rule 4 default-fills a best-guess trigger
 *  even for a bare question with no email context at all, so a truthy
 *  trigger is not a reliable "something was built" signal; `actions` never
 *  gets defaulted that way (see copilot.py's matching engine-side
 *  suppression for the same reasoning). A question that ALSO adds a real
 *  action (e.g. "what does assignment support, also tag emails from acme as
 *  VIP") still gets its card — only "no actions at all" is the tell, not "a
 *  question was asked". */
export function hasRuleCard(t: TurnState): boolean {
  // Track A (an app_feature match) has no `actions` field AT ALL -- must
  // short-circuit before touching it, the same guard the final return
  // below already relied on (t.track !== "feature" comes first there);
  // the capability-question check below was added later and, unlike that
  // return, evaluated `.actions.length` unconditionally -- a real crash a
  // live test hit the moment a Track A badge (e.g. "Create a Task from
  // Hiver") was clicked.
  if (t.track === "feature") return false;
  const builtNothing = t.spec.actions.length === 0;
  if (t.capability_answer && builtNothing) return false;
  // The ClickUp "create a task" native action must not surface a card
  // filled in with a silent "runs on everything" guess -- the admin has to
  // say WHEN to create the task and WHAT to look for FIRST (engine/
  // automation/validator.py's clickup_create_task-only scope override, plus
  // extract.py's rule 22 leaving trigger null for it). A spec that is JUST
  // this one still-unconfirmed action holds the card back; any OTHER action
  // in the same spec (or this one once trigger+scope are both given) shows
  // as normal.
  const clickupActions = t.spec.actions.filter(
    (a) => a.native_action_id === "clickup_create_task");
  const onlyUnconfirmedClickupTask = clickupActions.length > 0
    && clickupActions.length === t.spec.actions.length
    && (!t.spec.trigger
        || (!t.spec.scope_confirmed && t.spec.condition_groups.length === 0));
  if (onlyUnconfirmedClickupTask) return false;
  return !t.no_intent || Boolean(t.spec.trigger) || t.spec.actions.length > 0;
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
  // "you want X, I can do that via Y — here's how": set only on the turn a
  // capability is first matched (engine-side gated, not re-derived here) —
  // leads whichever branch below actually runs, Track A or B alike.
  const mapping = t.mapping_explanation ?? "";
  const withMapping = (line: string) => (mapping ? `${mapping}\n\n${line}` : line);
  if (t.track === "feature" && t.feature_request) {
    // Track A: a completely different shape from an automation turn — no
    // WHEN/IF/THEN. The FeatureCard renders the running setup progress;
    // this is just the lead-in line + (mid-setup) the one open question,
    // the questionnaire below carries the actual answer options.
    const fr = t.feature_request;
    if (fr.status === "complete" && fr.feature) {
      const line = `${fr.feature.name} is set up — review it below.`;
      return withMapping(
        t.feature_test_suggestion ? `${line}\n\n${t.feature_test_suggestion}` : line
      );
    }
    if (fr.status === "invalid")
      return withMapping("This isn't usable yet: " + fr.errors.join("; ") + ".");
    return withMapping(fr.questions.length
      ? `To finish setting this up: ${fr.questions[0]}`
      : "Setting this up — see below.");
  }
  if (mapping) parts.push(mapping);
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
