import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportSplitPanel } from "@/components/report/ReportSplitPanel";
import { ClarificationApprovalCard } from "@/components/stages/ClarificationApprovalCard";
import { ResearchProgressTimeline } from "@/components/stages/ResearchProgressTimeline";

// VerdictCard's prose and the in-progress section preview both reveal text
// via useTypewriter, which starts empty and animates on a rAF loop --
// forcing prefers-reduced-motion makes it render fully immediately, so
// these component tests can assert on complete text without fake timers
// (useTypewriter's own animation behavior is covered separately in
// useTypewriter.test.ts).
beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia;
});

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
          verdict: null,
          unresolved_gaps: [],
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
                      stance: "supports",
                    },
                  ],
                },
              ],
            },
          ],
        }}
        sections={[]}
        verdict={null}
        unresolvedGaps={[]}
        onDownloadPdf={vi.fn()}
      />,
    );
    expect(screen.getByText("Final Market Research Report")).toBeInTheDocument();
    expect(screen.getByText("Market Overview")).toBeInTheDocument();
    expect(screen.getByText("The market is growing.")).toBeInTheDocument();
    // The real title ("Example") is shown, not the bare domain fallback --
    // this is the Stage 5b fix (title was hardcoded to source.domain).
    expect(screen.getByText("Example")).toBeInTheDocument();
    expect(screen.queryByText("example.com")).not.toBeInTheDocument();
  });

  it("does not reserve a verdict slot when nothing has started streaming", () => {
    render(
      <ReportSplitPanel
        finalReport={null}
        sections={[]}
        verdict={null}
        unresolvedGaps={[]}
        onDownloadPdf={vi.fn()}
      />,
    );
    expect(screen.queryByText("The verdict")).not.toBeInTheDocument();
  });

  it("shows a pending verdict state once sections start streaming", () => {
    render(
      <ReportSplitPanel
        finalReport={null}
        sections={[{ sectionId: "s1", title: "Problem Context", status: "streaming", partialText: "Some text" }]}
        verdict={null}
        unresolvedGaps={[]}
        onDownloadPdf={vi.fn()}
      />,
    );
    expect(screen.getByText("Weighing the evidence…")).toBeInTheDocument();
  });

  it("renders the full verdict as prose, with case against and flip condition", () => {
    render(
      <ReportSplitPanel
        finalReport={null}
        sections={[{ sectionId: "s1", title: "Problem Context", status: "streaming", partialText: "Some text" }]}
        verdict={{
          verdict: "reshape",
          holding: "Go, but only in the underserved segment.",
          flip_condition: "If a top incumbent adds this feature within a year.",
          confidence: "medium",
          payload: {
            case_for_prose: "Demand is real and validated.",
            case_against_prose: "Incumbents already own distribution.",
            which_won: "The distribution gap outweighs the demand.",
          },
        }}
        unresolvedGaps={["What the typical price point should be."]}
        onDownloadPdf={vi.fn()}
      />,
    );
    expect(screen.getByText("Go, but only in the underserved segment.")).toBeInTheDocument();
    expect(screen.getByText("Demand is real and validated.")).toBeInTheDocument();
    expect(screen.getByText("Incumbents already own distribution.")).toBeInTheDocument();
    expect(screen.getByText("If a top incumbent adds this feature within a year.")).toBeInTheDocument();
    expect(screen.getByText("What the typical price point should be.", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("Weighing the evidence…")).not.toBeInTheDocument();
  });

  it("renders a GFM markdown table as a real table, not raw pipe syntax", () => {
    // Fix-audit: the PDF export now renders chunk.text's markdown tables
    // as real tables (app/services/markdown_pdf.py) -- the web view must
    // render the identical string the same way, not as literal "| a | b |"
    // text, which react-markdown alone (without remark-gfm) would do.
    render(
      <ReportSplitPanel
        finalReport={{
          report_id: "rep-1",
          status: "EXPORTED",
          title: "Report",
          verdict: null,
          unresolved_gaps: [],
          sections: [
            {
              section_id: "s1",
              title: "Existing Solutions",
              order_index: 0,
              chunks: [
                {
                  chunk_id: "c1",
                  order_index: 0,
                  text: "| Vendor | Price |\n| --- | --- |\n| Acme | $29/mo |\n",
                  citations: [],
                },
              ],
            },
          ],
        }}
        sections={[]}
        verdict={null}
        unresolvedGaps={[]}
        onDownloadPdf={vi.fn()}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Vendor" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Acme" })).toBeInTheDocument();
    // Not left as literal markdown syntax anywhere in the document.
    expect(screen.queryByText("| Vendor | Price |", { exact: false })).not.toBeInTheDocument();
  });
});
