"use client";

import { useEffect, useRef, useState } from "react";

// Gap-closing plan Stage 5d: the report is read in-app, long before the PDF
// exists -- section_chunk events already stream real paragraph text in.
// This renders that arrival as continuous writing instead of paragraphs
// popping in as whole blocks. Word granularity, not character: ~3000 words
// at character-by-character speed reads as a gimmick, not "being written".
const DEFAULT_WORDS_PER_SECOND = 45;
// If the reader tabbed away and the gap between shown and target text grows
// large, accelerate rather than making them watch minutes of catch-up typing.
const CATCH_UP_THRESHOLD_WORDS = 40;
const CATCH_UP_MULTIPLIER = 6;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Splits into words while preserving the whitespace between them, so
// re-joining a prefix of the array reproduces the original spacing exactly.
function splitKeepingWhitespace(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [];
}

/**
 * Reveals `targetText` word by word at `wordsPerSecond`. Safe to call with a
 * `targetText` that keeps growing (e.g. more section_chunk text appended
 * mid-reveal) -- the reveal just keeps extending toward the new, longer
 * target instead of restarting. The animation loop runs continuously for
 * the component's lifetime (not restarted per text change) and always
 * reads the latest target via a ref, so appending text never interrupts
 * an in-flight animation frame.
 */
export function useTypewriter(
  targetText: string,
  wordsPerSecond: number = DEFAULT_WORDS_PER_SECOND,
): string {
  // A ref read during render isn't allowed (react-hooks/refs) even though
  // this value never changes after mount -- useState's lazy initializer is
  // the correct place to compute a render-time constant like this once.
  const [reducedMotion] = useState(prefersReducedMotion);
  const [displayed, setDisplayed] = useState("");

  const targetRef = useRef(targetText);
  const shownCountRef = useRef(0);

  // Cheap: just keeps the loop's view of the target current. Does not
  // touch the animation loop below, so appending text never cancels or
  // restarts an in-flight animation frame. No-op (and no setState call at
  // all, so nothing for react-hooks/set-state-in-effect to flag) when
  // reduced motion is active -- that case returns targetText directly
  // below instead of going through displayed/setDisplayed.
  useEffect(() => {
    targetRef.current = targetText;
  }, [targetText]);

  // The animation loop itself: mount/unmount only.
  useEffect(() => {
    if (reducedMotion) return;

    let frameId: number;
    let lastTick: number | null = null;
    // Fractional words earned since the last whole-word reveal. Without
    // this, flooring each frame's advance to "at least 1 word" (a tempting
    // fix for "0 words revealed on a fast frame") silently sets an EFFECTIVE
    // floor of ~1 word per frame -- at 60fps that's 60 words/sec minimum,
    // regardless of the configured rate. Accumulating fractional progress
    // and only committing whole words once it crosses 1.0 is frame-rate
    // independent at any configured wordsPerSecond.
    let wordAccumulator = 0;

    const tick = (now: number) => {
      const words = splitKeepingWhitespace(targetRef.current);
      shownCountRef.current = Math.min(shownCountRef.current, words.length);

      if (shownCountRef.current < words.length) {
        const last = lastTick ?? now;
        const elapsedSeconds = (now - last) / 1000;

        const behind = words.length - shownCountRef.current;
        const rate =
          behind > CATCH_UP_THRESHOLD_WORDS
            ? wordsPerSecond * CATCH_UP_MULTIPLIER
            : wordsPerSecond;

        wordAccumulator += rate * elapsedSeconds;
        const wholeWords = Math.floor(wordAccumulator);
        if (wholeWords > 0) {
          wordAccumulator -= wholeWords;
          shownCountRef.current = Math.min(shownCountRef.current + wholeWords, words.length);
          setDisplayed(words.slice(0, shownCountRef.current).join(""));
        }
      }

      lastTick = now;
      frameId = requestAnimationFrame(tick);
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [wordsPerSecond, reducedMotion]);

  return reducedMotion ? targetText : displayed;
}
