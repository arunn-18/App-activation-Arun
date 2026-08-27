"use client";

import type { TurnState } from "@/lib/api";

/** Structured, clickable capability chips for a capability question —
 *  engine/docent.py's relevant_capabilities(), the structured sibling of
 *  capability_answer's prose. A live test asked for exactly this: asking
 *  "what capabilities does ClickUp integration provide?" got a prose
 *  answer plus a misleading RuleCard with an "excluded" question in it,
 *  instead of anything naming the real capabilities that answer the
 *  question. Renders nothing when the topic doesn't name discrete
 *  capabilities (most topics — assignment, triggers, conditions — are
 *  generic rule-building primitives with no single badge-able entry).
 *
 *  Clicking a badge sends its own name as the next message — the same
 *  "bare capability name routes correctly" discipline the Apps panel's own
 *  suggestion chips already rely on (see apps/page.tsx's suggestionPrompt). */
export default function CapabilityBadges({
  badges,
  onTry,
  disabled,
}: {
  badges: NonNullable<TurnState["capability_badges"]>;
  onTry: (text: string) => void;
  disabled?: boolean;
}) {
  if (!badges.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {badges.map((b) => (
        <button
          key={b.id}
          disabled={disabled}
          onClick={() => onTry(b.name)}
          className="rounded-full border border-hairline px-2.5 py-1 text-[11.5px] text-ink-soft transition-colors hover:border-ink-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
        >
          {b.name}
        </button>
      ))}
    </div>
  );
}
