import { PdfDownloadButton } from "@/components/report/PdfDownloadButton";
import type { ReportState, SectionItem } from "@/lib/state/chatFlowStore";

type ReportSplitPanelProps = {
  finalReport: ReportState | null;
  sections: SectionItem[];
  onDownloadPdf: () => void;
};

export function ReportSplitPanel({
  finalReport,
  sections,
  onDownloadPdf,
}: ReportSplitPanelProps) {
  return (
    <aside className="flex h-full min-h-[300px] w-full flex-col rounded-2xl border border-zinc-700 bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <h2 className="text-sm font-semibold text-zinc-200">Final report</h2>
        <PdfDownloadButton onDownload={onDownloadPdf} />
      </div>
      <div className="overflow-y-auto p-4">
        {finalReport ? (
          <>
            <h3 className="text-lg font-semibold text-zinc-100">{finalReport.title}</h3>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-300">
              {finalReport.content}
            </p>
          </>
        ) : sections.length ? (
          <>
            <h3 className="text-lg font-semibold text-zinc-100">
              Streaming section drafts
            </h3>
            <div className="mt-3 space-y-3">
              {sections.map((section) => (
                <article key={section.sectionId} className="rounded-xl bg-zinc-900 p-3">
                  <p className="text-sm font-medium text-zinc-100">{section.title}</p>
                  <p className="mt-2 text-xs leading-5 text-zinc-300">
                    {section.partialText}
                  </p>
                </article>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-zinc-400">
            Report output will appear here when section and assembler stages complete.
          </p>
        )}
      </div>
    </aside>
  );
}
