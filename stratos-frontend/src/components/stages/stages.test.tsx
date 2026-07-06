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
    expect(screen.getByText("Clarification complete")).toBeInTheDocument();
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

  it("renders read only final report panel", () => {
    render(
      <ReportSplitPanel
        finalReport={{
          title: "Final Market Research Report",
          content: "Report body",
        }}
        sections={[]}
        onDownloadPdf={vi.fn()}
      />,
    );
    expect(screen.getByText("Final Market Research Report")).toBeInTheDocument();
    expect(screen.getByText("Report body")).toBeInTheDocument();
  });
});
