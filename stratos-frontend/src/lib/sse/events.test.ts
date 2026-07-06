import { describe, expect, it } from "vitest";

import { parseEventData } from "@/lib/sse/events";

describe("parseEventData", () => {
  it("parses valid envelope", () => {
    const result = parseEventData(
      JSON.stringify({ type: "research_started", payload: { report_id: "r1" } }),
    );

    expect(result).toEqual({
      type: "research_started",
      payload: { report_id: "r1" },
    });
  });

  it("returns null for invalid json", () => {
    expect(parseEventData("{broken")).toBeNull();
  });
});
