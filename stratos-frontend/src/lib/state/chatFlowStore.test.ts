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

  it("stores the full verdict and unresolved gaps on verdict_ready", () => {
    const actions = eventToActions({
      type: "verdict_ready",
      payload: {
        report_id: "rep-1",
        verdict: "reshape",
        holding: "Go, but only in the underserved segment.",
        case_for_prose: "Demand is real [CIT-001].",
        case_against_prose: "Incumbents already own distribution [CIT-002].",
        which_won: "The distribution gap outweighs the demand [CIT-002].",
        flip_condition: "If a top incumbent adds this feature within a year.",
        confidence: "medium",
        unresolved_gaps: ["What the typical price point should be."],
      },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.verdict?.verdict).toBe("reshape");
    expect(finalState.verdict?.holding).toBe("Go, but only in the underserved segment.");
    expect(finalState.verdict?.payload.case_against_prose).toContain("Incumbents");
    expect(finalState.unresolvedGaps).toEqual(["What the typical price point should be."]);
  });

  it("ignores verdict_ready with an unrecognized verdict value", () => {
    const actions = eventToActions({
      type: "verdict_ready",
      payload: { verdict: "not_a_real_verdict" },
    });
    expect(actions.some((a) => a.type === "SET_VERDICT")).toBe(false);
  });

  it("treats verdict_failed as non-fatal (report still assembles)", () => {
    const actions = eventToActions({
      type: "verdict_failed",
      payload: { report_id: "rep-1", error: "LLM validation exhausted" },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).not.toBe("failed");
    expect(finalState.error).toBeNull();
  });

  it("does not regress stage back to researching for post-writing progress events", () => {
    // Regression check: sections_done/report_assembled fire well after
    // section_writing_started already moved the stage to
    // streamingSections. They must not push SET_STAGE researching.
    for (const eventType of ["sections_done", "report_assembled", "verdict_started", "verdict_ready"]) {
      const actions = eventToActions({ type: eventType, payload: { report_id: "rep-1" } });
      const stageActions = actions.filter((a) => a.type === "SET_STAGE");
      expect(stageActions).toEqual([]);
    }
  });

  it("still sets stage to researching for pre-writing progress events", () => {
    const actions = eventToActions({
      type: "scanning_trends",
      payload: { report_id: "rep-1" },
    });
    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).toBe("researching");
  });

  it("marks a _ready progress event as done, not stuck on running", () => {
    const actions = eventToActions({
      type: "trend_ready",
      payload: { report_id: "rep-1" },
    });
    const progressAction = actions.find((a) => a.type === "ADD_PROGRESS");
    expect(progressAction?.type).toBe("ADD_PROGRESS");
    if (progressAction?.type === "ADD_PROGRESS") {
      expect(progressAction.event.status).toBe("done");
    }
  });

  it("backfills verdict and unresolvedGaps from SET_FINAL_REPORT", () => {
    const finalState = chatFlowReducer(initialState, {
      type: "SET_FINAL_REPORT",
      report: {
        report_id: "rep-1",
        status: "EXPORTED",
        title: "Final Report",
        verdict: {
          verdict: "build",
          holding: "Go.",
          flip_condition: null,
          confidence: "high",
          payload: {},
        },
        unresolved_gaps: ["Some open question."],
        sections: [],
      },
    });

    expect(finalState.verdict?.verdict).toBe("build");
    expect(finalState.unresolvedGaps).toEqual(["Some open question."]);
  });
});
