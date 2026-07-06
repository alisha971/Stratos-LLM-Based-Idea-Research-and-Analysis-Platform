import { describe, expect, it } from "vitest";

import { eventToActions, chatFlowReducer, initialState } from "@/lib/state/chatFlowStore";

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

  it("creates streaming placeholder after research_done", () => {
    const actions = eventToActions({
      type: "research_done",
      payload: { report_id: "rep-1" },
    });

    const finalState = actions.reduce(chatFlowReducer, initialState);
    expect(finalState.stage).toBe("streamingSections");
    expect(finalState.sectionOrder.length).toBe(1);
  });
});
