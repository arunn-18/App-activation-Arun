"use client";

import { useEffect, useRef, useState } from "react";

/** Progressive reveal of an assistant reply.
 *
 *  Note what this is NOT: the engine composes its prose in code from the
 *  validated rule (lib/api assistantText), and the model only ever emits
 *  structured JSON — so there is no token stream to pipe through. This is a
 *  presentation effect over text that already arrived whole, which also means
 *  it works in production, where Vercel's Python functions can't stream at all.
 *
 *  Reveal is time-boxed rather than fixed-per-character: a long reply finishes
 *  in about the same time as a short one, so the effect never becomes a wait. */
export default function StreamedText({
  text,
  animate,
  onDone,
  className,
}: {
  text: string;
  animate: boolean;
  onDone?: () => void;
  className?: string;
}) {
  const [shown, setShown] = useState(() => (animate ? 0 : text.length));
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    if (!animate) {
      setShown(text.length);
      return;
    }
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setShown(text.length);
      doneRef.current?.();
      return;
    }
    // rAF + elapsed time, not a fixed per-tick step: background tabs throttle
    // timers to ~1Hz, which turned a 1s reveal into a minute-long crawl. Driving
    // from the clock means a tab that was away simply catches up on return.
    const TARGET_MS = 900; // whole reply lands in ~1s regardless of length
    const start = performance.now();
    let raf = 0;
    setShown(0);
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / TARGET_MS);
      setShown(Math.floor(p * text.length));
      if (p < 1) raf = requestAnimationFrame(tick);
      else doneRef.current?.();
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text, animate]);

  return (
    <div className={className}>
      {text.slice(0, shown)}
      {shown < text.length && (
        <span className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] animate-pulse bg-ink-soft align-baseline" />
      )}
    </div>
  );
}
