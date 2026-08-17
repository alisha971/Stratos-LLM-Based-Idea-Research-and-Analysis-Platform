import { describe, expect, it } from "vitest";

import {
  chatFlowReducer,
  eventToActions,
  initialState,
} from "@/lib/state/chatFlowStore";

describe("eventToActions", () => {
  it("moves to awaiting consent and stores summary", () => {
    const actions = eventToActions({
      type: "clarification_consent_requested",
      payload: { summary: "You want an XAI startup analysis." },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).toBe("awaitingConsent");
    expect(finalState.summaryForConsent).toContain("XAI startup");
  });

  it("stores report id and section skeletons on outline_ready", () => {
    const actions = eventToActions({
      type: "outline_ready",
      payload: {
        report_id: "rep-1",
        sections: [
          { section_id: "s1", title: "Market Overview", order_index: 0 },
          { section_id: "s2", title: "Competitors", order_index: 1 },
        ],
      },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.reportId).toBe("rep-1");
    expect(finalState.sectionOrder).toEqual(["s1", "s2"]);
    expect(finalState.sectionsById["s1"].status).toBe("pending");
  });

  it("appends (not replaces) streaming section chunks keyed by section_id", () => {
    const first = eventToActions({
      type: "section_chunk",
      payload: { section_id: "s1", text: "Hello " },
    });
    const second = eventToActions({
      type: "section_chunk",
      payload: { section_id: "s1", text: "world" },
    });

    const finalState = [...first, ...second].reduce(
      chatFlowReducer,
      initialState,
    );
    expect(finalState.sectionsById["s1"].partialText).toBe("Hello world");
    expect(finalState.stage).toBe("streamingSections");
  });

  it("marks failure and stores error on export_failed", () => {
    const actions = eventToActions({
      type: "export_failed",
      payload: { report_id: "rep-1", error: "PDF render crashed" },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).toBe("failed");
    expect(finalState.error).toBe("PDF render crashed");
  });

  it("treats trend_failed as non-fatal (pipeline continues)", () => {
    const actions = eventToActions({
      type: "trend_failed",
      payload: { report_id: "rep-1", error: "provider timeout" },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).not.toBe("failed");
  });

  it("moves to reportReady and stores report id on export_done", () => {
    const actions = eventToActions({
      type: "export_done",
      payload: { report_id: "rep-9" },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).toBe("reportReady");
    expect(finalState.reportId).toBe("rep-9");
  });
});
