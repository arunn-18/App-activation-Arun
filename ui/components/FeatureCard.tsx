"use client";

import type { FeatureRequest } from "@/lib/api";

const STATUS_STYLE: Record<FeatureRequest["status"], string> = {
  complete: "bg-bone text-ink",
  invalid: "bg-destructive-soft text-destructive",
};
const STATUS_LABEL: Record<FeatureRequest["status"], string> = {
  complete: "Enabled",
  invalid: "Blocked",
};

/** Track A's card — an app_feature ask (engine/schema.py FEATURES), resolved
 *  through engine/features.py rather than the automation validator. Kept as
 *  its own small component rather than a RuleCard variant: there is no
 *  trigger/conditions/actions to render, no draft-vs-final distinction, and
 *  no "apply this rule" step — a feature is either usable now (its
 *  prerequisites are met) or it isn't, and that's the whole card. */
export default function FeatureCard({
  featureRequest,
}: {
  featureRequest: FeatureRequest;
}) {
  const feat = featureRequest.feature;
  const name = feat?.name ?? featureRequest.feature_id ?? "App feature";

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
