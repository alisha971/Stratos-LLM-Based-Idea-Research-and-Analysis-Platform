import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportSplitPanel } from "@/components/report/ReportSplitPanel";
import { ClarificationApprovalCard } from "@/components/stages/ClarificationApprovalCard";
import { ResearchProgressTimeline } from "@/components/stages/ResearchProgressTimeline";

describe("stage components", () => {
  it("renders clarification approval summary", () => {
    render(
      <ClarificationApprovalCard
        summary="Summary text"
        onEdit={vi.fn()}
        onStartResearch={vi.fn()}
      />,
    );
    expect(screen.getByText("Here’s what I’ll research")).toBeInTheDocument();
    expect(screen.getByText("Summary text")).toBeInTheDocument();
  });

  it("renders research timeline events", () => {
    render(
      <ResearchProgressTimeline
        events={[
          {
            id: "1",
            label: "Research pipeline started",
            status: "running",
            timestamp: new Date().toISOString(),
          },
        ]}
      />,
    );
    expect(screen.getByText("Research pipeline started")).toBeInTheDocument();
  });

  it("renders the final report with sections and citations", () => {
    render(
      <ReportSplitPanel
        finalReport={{
          report_id: "rep-1",
          status: "EXPORTED",
          title: "Final Market Research Report",
          sections: [
            {
              section_id: "s1",
              title: "Market Overview",
              order_index: 0,
              chunks: [
                {
                  chunk_id: "c1",
                  order_index: 0,
                  text: "The market is growing.",
                  citations: [
                    {
                      marker: "CIT-001",
                      url: "https://example.com",
                      domain: "example.com",
                      title: "Example",
                    },
                  ],
                },
              ],
            },
          ],
        }}
        sections={[]}
        onDownloadPdf={vi.fn()}
      />,
    );
    expect(screen.getByText("Final Market Research Report")).toBeInTheDocument();
    expect(screen.getByText("Market Overview")).toBeInTheDocument();
    expect(screen.getByText("The market is growing.")).toBeInTheDocument();
    expect(screen.getByText("example.com")).toBeInTheDocument();
  });
});
