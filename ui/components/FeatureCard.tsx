"use client";

import type { FeatureRequest } from "@/lib/api";

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
}: {
  featureRequest: FeatureRequest;
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
