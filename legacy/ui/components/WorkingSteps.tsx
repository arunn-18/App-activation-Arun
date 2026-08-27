// ARCHIVED (2026-08-27, App Activation charter): used only by the general
// Automations panel's live pipeline-progress display (legacy/ui/lib/
// api-automations.ts's ProgressEvent/progressLabel/finalStepLabel) — see
// legacy/ui/app/page.tsx's note. Kept for reference, not wired into the
// active build.

"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

/** Live view while the pipeline runs. Collapsed to a single shimmering
 *  "WORKING" row — the step list is progress detail, not something to read at
 *  speed, so it lives behind the disclosure. Every listed step has actually
 *  started; the last one is in progress. */
export function WorkingLive({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mr-4">
      <div className="w-fit min-w-48 rounded-lg border border-hairline bg-surface px-3 py-2">
        <CollapsibleTrigger className="flex w-full items-center gap-2 text-left">
          <span className="shimmer font-mono text-[10px] font-semibold tracking-[0.16em] text-muted-foreground">
            WORKING
          </span>
          <span className="text-[11px] text-muted-foreground">
            · {steps.length} step{steps.length === 1 ? "" : "s"}
          </span>
          {open ? (
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="mt-1.5 space-y-1 border-t border-hairline pt-1.5">
            {steps.map((s, i) => {
              const active = i === steps.length - 1;
              return (
                <li key={i} className="flex items-center gap-2 text-[12px]">
                  {active ? (
                    <span className="size-3 shrink-0" />
                  ) : (
                    <Check className="size-3 shrink-0 text-ink-soft" />
                  )}
                  <span className={active ? "shimmer text-ink-soft" : "text-muted-foreground"}>
                    {s}
                  </span>
                </li>
              );
            })}
          </ul>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

/** Collapsed record of a finished turn — Amplitude's "Finished working ›" row.
 *  The intent restatement lives in the reply prose, not here. */
export function WorkingSummary({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mr-4">
      <div className="w-fit min-w-56 rounded-lg border border-hairline bg-surface px-3 py-2">
        <CollapsibleTrigger className="flex w-full items-center gap-2 text-left">
          <Check className="size-3.5 shrink-0 text-ink-soft" />
          <span className="text-[12px] text-ink-soft">Finished working</span>
          <span className="text-[12px] text-muted-foreground">
            · {steps.length} steps
          </span>
          {open ? (
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
          )}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="mt-1.5 space-y-1 border-t border-hairline pt-1.5">
            {steps.map((s, i) => (
              <li key={i} className="flex items-center gap-2 text-[12px] text-muted-foreground">
                <Check className="size-3 shrink-0 text-ink-soft" />
                {s}
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
