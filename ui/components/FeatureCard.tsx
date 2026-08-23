"use client";

import { useEffect, useState } from "react";
import type { FeatureRequest, TestableConversation, TestCreateResult } from "@/lib/api";
import { Button } from "@/components/ui/button";

const STATUS_STYLE: Record<FeatureRequest["status"], string> = {
  complete: "bg-bone text-ink",
  needs_info: "bg-bone text-ink-soft",
  invalid: "bg-destructive-soft text-destructive",
};
const STATUS_LABEL: Record<FeatureRequest["status"], string> = {
  complete: "Enabled",
  needs_info: "Setting up",
  invalid: "Blocked",
};

// The engine has no vocabulary endpoint for feature display names yet
// (only trigger/property labels, via /api/vocabulary) — same fallback
// pattern RuleCard uses for the connector recipe's name.
const FEATURE_NAMES: Record<string, string> = {
  salesforce_account_contact_details: "View account & contact details",
};

/** Track A's card — a real multi-turn setup (engine/features.resolve_setup:
 *  Authentication -> pick records -> pick fields per record -> enable for
 *  the shared inbox(es) it applies to), not a single yes/no check. Kept as
 *  its own component rather than a RuleCard variant: there is no
 *  trigger/conditions/actions to render, and progress accumulates as
 *  objects/objects+fields/inboxes rather than WHEN/IF/THEN. The actual
 *  questions (connect CTA, record picker, field picker, inbox picker)
 *  render below this card via the SAME QuestionForm the automation flow
 *  uses — this card is the running summary, not the input. */
export default function FeatureCard({
  featureRequest,
  onTestCreate,
  fetchTestConversations,
}: {
  featureRequest: FeatureRequest;
  /** capability 7 for a WRITE feature — submits the test form's values and
   *  resolves to the real (mock) create result. Omitted entirely on a page
   *  that doesn't wire up the endpoint; the form simply doesn't render then,
   *  same "don't offer what isn't there" stance as everything else here. */
  onTestCreate?: (fieldValues: Record<string, string>) => Promise<TestCreateResult>;
  /** capability 7's conversation picker — real mailbox conversations to
   *  choose from BEFORE the create-form appears (never skipped past
   *  straight into the form; a live test asked for exactly this order). */
  fetchTestConversations?: () => Promise<TestableConversation[]>;
}) {
  const feat = featureRequest.feature;
  const progress = featureRequest.progress ?? {};
  const name =
    feat?.name ?? FEATURE_NAMES[featureRequest.feature_id ?? ""] ?? "App feature";
  const fieldsByObject = feat?.fields_by_object ?? progress.fields_by_object ?? {};
  const objects = feat?.objects ?? progress.objects ?? [];
  const inboxes = feat?.inboxes ?? progress.inboxes ?? [];

  return (
    <div className="overflow-hidden rounded-xl border border-hairline bg-card">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2.5">
        <span className="font-mono text-[11px] font-semibold tracking-[0.18em] text-muted-foreground">
          APP FEATURE
        </span>
        <span
          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${STATUS_STYLE[featureRequest.status]}`}
        >
          {STATUS_LABEL[featureRequest.status]}
        </span>
      </div>

      <div className="px-4 py-3">
        <p className="text-[14px] font-medium text-ink">{name}</p>
        {feat?.description && (
          <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">
            {feat.description}
          </p>
        )}
      </div>

      {(progress.connected != null || objects.length > 0 || inboxes.length > 0) && (
        <div className="space-y-1.5 border-t border-hairline px-4 py-3 text-[12.5px]">
          <p className="text-ink-soft">
            <span className="font-mono text-[11px] font-semibold text-muted-foreground">
              CONNECTED
            </span>{" "}
            {progress.connected ? "yes" : "not yet"}
          </p>
          {objects.length > 0 && (
            <p className="text-ink-soft">
              <span className="font-mono text-[11px] font-semibold text-muted-foreground">
                RECORDS
              </span>{" "}
              {objects.join(", ")}
            </p>
          )}
          {Object.entries(fieldsByObject).map(([obj, fields]) => (
            <p key={obj} className="text-ink-soft">
              <span className="font-mono text-[11px] font-semibold text-muted-foreground">
                {obj.toUpperCase()} FIELDS
              </span>{" "}
              {fields.join(", ")}
            </p>
          ))}
          {inboxes.length > 0 && (
            <p className="text-ink-soft">
              <span className="font-mono text-[11px] font-semibold text-muted-foreground">
                ENABLED FOR
              </span>{" "}
              {inboxes.join(", ")}
            </p>
          )}
        </div>
      )}

      {featureRequest.preview && (
        <FeaturePreviewStrip preview={featureRequest.preview} />
      )}

      {featureRequest.status === "complete" && feat?.kind === "write" && onTestCreate && (
        <WriteTestForm
          fieldsByObject={fieldsByObject}
          onTestCreate={onTestCreate}
          fetchTestConversations={fetchTestConversations}
        />
      )}

      {featureRequest.status === "invalid" && featureRequest.errors.length > 0 && (
        <div className="border-t border-hairline bg-destructive-soft px-4 py-2.5">
          <p className="text-[12px] font-semibold text-destructive">
            Not usable yet:
          </p>
          <ul className="mt-1 space-y-0.5">
            {featureRequest.errors.map((e, i) => (
              <li key={i} className="text-[12.5px] text-destructive">
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}

      {featureRequest.status === "complete" && (
        <div className="border-t border-hairline bg-bone px-4 py-2.5">
          <span className="text-[12px] text-ink-soft">
            (demo: recorded here, not actually toggled in Hiver)
          </span>
        </div>
      )}
    </div>
  );
}

/** "Test on a real conversation" (v2.13, capability 7): proof the feature
 *  shows real data for a real contact, the Track A analogue of RuleCard's
 *  TestRunStrip — a courtesy shown once the admin names a real contact to
 *  preview against, never required for the card above to say "Enabled". */
function FeaturePreviewStrip({
  preview,
}: {
  preview: NonNullable<import("@/lib/api").FeatureRequest["preview"]>;
}) {
  if (preview.status === "no_match")
    return (
      <div className="border-t border-hairline bg-destructive-soft px-4 py-2.5">
        <span className="text-[12.5px] text-destructive">
          <span className="font-semibold">Test run: no match</span> — {preview.reason}.
        </span>
      </div>
    );
  return (
    <div className="space-y-1.5 border-t border-hairline px-4 py-3 text-[12.5px]">
      <p className="font-medium text-ink">
        Test run against <span className="font-mono text-[12px]">{preview.contact_email}</span>:
      </p>
      {Object.entries(preview.values_by_object).map(([obj, values]) => (
        <p key={obj} className="text-ink-soft">
          <span className="font-mono text-[11px] font-semibold text-muted-foreground">
            {obj.toUpperCase()}
          </span>{" "}
          {Object.entries(values)
            .map(([k, v]) => `${k}: ${v ?? "—"}`)
            .join(", ")}
        </p>
      ))}
    </div>
  );
}

/** "Test on a real conversation" (capability 7) for a WRITE feature: a
 *  view feature's test shows EXISTING data (FeaturePreviewStrip above); a
 *  write feature creates something new, so testing it means actually
 *  submitting values and creating a real (mock) record — the write
 *  analogue, not a variant of the same strip.
 *
 *  TWO STEPS, in order — a live test explicitly asked for the conversation
 *  picker to come FIRST, matching the real Hiver Salesforce panel (open a
 *  conversation, THEN its create-object form appears), not a bare form with
 *  no conversation context at all:
 *    1. pick a real conversation (mailbox_lookup.testable_conversations,
 *       the SAME real-conversation set a view feature's preview offers)
 *    2. only then does the field-value form for THAT conversation appear */
function WriteTestForm({
  fieldsByObject,
  onTestCreate,
  fetchTestConversations,
}: {
  fieldsByObject: Record<string, string[]>;
  onTestCreate: (fieldValues: Record<string, string>) => Promise<TestCreateResult>;
  fetchTestConversations?: () => Promise<TestableConversation[]>;
}) {
  const object = Object.keys(fieldsByObject)[0];
  const labels = fieldsByObject[object] ?? [];
  const [conversations, setConversations] = useState<TestableConversation[] | null>(null);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [selected, setSelected] = useState<TestableConversation | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TestCreateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!fetchTestConversations) return;
    fetchTestConversations()
      .then(setConversations)
      .catch((e) => setConversationsError(e instanceof Error ? e.message : String(e)));
  }, [fetchTestConversations]);

  if (!object || labels.length === 0) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await onTestCreate(values));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  // step 1: no picker wired up at all (a page that hasn't fetched it) — fall
  // back to the form directly, same graceful "don't offer what isn't there"
  // stance as the rest of this component. Otherwise a conversation MUST be
  // picked before the form shows.
  if (fetchTestConversations && !selected) {
    return (
      <div className="space-y-2 border-t border-hairline px-4 py-3">
        <p className="text-[12.5px] font-medium text-ink">
          Test it — pick a real conversation to open the create-{object} form in:
        </p>
        {conversationsError && (
          <p className="text-[12px] text-destructive">{conversationsError}</p>
        )}
        {conversations === null && !conversationsError && (
          <p className="text-[12px] text-muted-foreground">Loading conversations…</p>
        )}
        {conversations?.length === 0 && (
          <p className="text-[12px] text-muted-foreground">
            No real conversations to test with yet.
          </p>
        )}
        <div className="space-y-1.5">
          {conversations?.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c)}
              className="block w-full rounded-lg border border-hairline bg-surface px-3 py-2 text-left text-[12.5px] transition-colors hover:border-ink-soft"
            >
              <span className="font-medium text-ink">{c.from}</span>{" "}
              <span className="text-ink-soft">— {c.subject}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  // step 2: the form, now scoped to the picked conversation.
  return (
    <div className="space-y-2.5 border-t border-hairline px-4 py-3">
      <p className="text-[12.5px] font-medium text-ink">
        {selected
          ? <>Creating a {object} for <span className="font-mono text-[12px]">{selected.from}</span> ({selected.subject}):</>
          : `Test it — create a real ${object} from these values:`}
      </p>
      {selected && (
        <button
          onClick={() => setSelected(null)}
          className="text-[11.5px] text-muted-foreground underline-offset-2 hover:underline"
        >
          Pick a different conversation
        </button>
      )}
      <form onSubmit={submit} className="space-y-2">
        {labels.map((label) => (
          <div key={label} className="flex items-center gap-2">
            <label className="w-36 shrink-0 text-[12px] text-ink-soft">{label}</label>
            <input
              value={values[label] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [label]: e.target.value }))}
              placeholder={`Enter ${label.toLowerCase()}`}
              className="min-w-0 flex-1 rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-[12.5px] outline-none focus:border-ink-soft"
            />
          </div>
        ))}
        <Button type="submit" size="sm" disabled={busy}>
          {busy ? "Creating…" : "Create"}
        </Button>
      </form>
      {error && <p className="text-[12px] text-destructive">{error}</p>}
      {result?.status === "error" && (
        <p className="text-[12px] text-destructive">{result.reason}</p>
      )}
      {result?.status === "ok" && (
        <p className="text-[12.5px] text-ink-soft">
          <span className="font-medium text-ink">{object} created</span> —{" "}
          {Object.entries(result.record ?? {})
            .map(([k, v]) => `${k}: ${v}`)
            .join(", ")}
        </p>
      )}
    </div>
  );
}
