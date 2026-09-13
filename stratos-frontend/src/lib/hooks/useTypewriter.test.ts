import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTypewriter } from "@/lib/hooks/useTypewriter";

function mockMatchMedia(reducedMotion: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reducedMotion && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

describe("useTypewriter", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
    mockMatchMedia(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts empty and reveals words over time", () => {
    const { result } = renderHook(() => useTypewriter("one two three four five", 50));

    expect(result.current).toBe("");

    act(() => {
      vi.advanceTimersByTime(1000); // 50 words/sec * 1s = well past 5 words
    });

    expect(result.current.trim()).toBe("one two three four five");
  });

  it("reveals a prefix of the words, not the whole text at once, at low elapsed time", () => {
    const { result } = renderHook(() =>
      useTypewriter("one two three four five six seven eight nine ten", 10),
    );

    act(() => {
      vi.advanceTimersByTime(200); // 10 words/sec * 0.2s = ~2 words
    });

    expect(result.current.trim().length).toBeGreaterThan(0);
    expect(result.current.trim()).not.toBe(
      "one two three four five six seven eight nine ten",
    );
  });

  it("extends toward newly appended text without resetting position", () => {
    const { result, rerender } = renderHook(
      ({ text }) => useTypewriter(text, 50),
      { initialProps: { text: "one two three" } },
    );

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.trim()).toBe("one two three");

    rerender({ text: "one two three four five" });

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.trim()).toBe("one two three four five");
  });

  it("catches up quickly on a large backlog instead of animating word by word", () => {
    const longText = Array.from({ length: 200 }, (_, i) => `word${i}`).join(" ");
    const { result } = renderHook(() => useTypewriter(longText, 10));

    act(() => {
      vi.advanceTimersByTime(1000); // at plain 10 wps this would only reach ~10 words
    });

    const shownWords = result.current.trim().split(/\s+/).length;
    expect(shownWords).toBeGreaterThan(20);
  });

  it("respects prefers-reduced-motion by rendering instantly", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTypewriter("one two three four five", 5));

    // No timer advance at all -- must already be fully shown.
    expect(result.current).toBe("one two three four five");
  });
});
