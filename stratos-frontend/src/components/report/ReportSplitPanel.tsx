import ReactMarkdown from "react-markdown";

import { PdfDownloadButton } from "@/components/report/PdfDownloadButton";
import type { ReportView } from "@/lib/api/orchestratorClient";
import type { SectionItem } from "@/lib/state/chatFlowStore";

type ReportSplitPanelProps = {
  finalReport: ReportView | null;
  sections: SectionItem[];
  onDownloadPdf: () => void;
  downloadDisabled?: boolean;
  onClose?: () => void;
};

export function ReportSplitPanel({
  finalReport,
  sections,
  onDownloadPdf,
  downloadDisabled = false,
  onClose,
}: ReportSplitPanelProps) {
  return (
    <aside className="flex h-full min-h-[300px] w-full flex-col bg-paper-raised">
      <div className="flex items-center justify-between border-b border-rule-strong px-6 py-3">
        <h2 className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
          The report
        </h2>
        <div className="flex items-center gap-2">
          <PdfDownloadButton onDownload={onDownloadPdf} disabled={downloadDisabled} />
          {onClose ? (
            <button
              onClick={onClose}
              aria-label="Close report panel"
              title="Close report panel"
              className="flex h-7 w-7 items-center justify-center text-ink-soft hover:bg-paper-sunken hover:text-ink"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              >
                <path d="M3 3l8 8M11 3l-8 8" />
              </svg>
            </button>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
        {finalReport ? (
          <>
            <h3 className="font-serif text-2xl font-medium leading-snug tracking-tight text-ink">
              {finalReport.title}
            </h3>
            <div className="mt-8 space-y-10">
              {finalReport.sections.map((section, index) => (
                <section key={section.section_id}>
                  <div className="flex items-baseline gap-3 border-b border-rule pb-2">
                    <span className="font-mono text-xs text-ink-faint">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <h4 className="font-serif text-lg font-medium text-ink">
                      {section.title}
                    </h4>
                  </div>
                  {section.chunks.map((chunk) => (
                    <div key={chunk.chunk_id} className="mt-3">
                      <div className="report-markdown text-sm leading-relaxed text-ink-soft">
                        {/* No rehype-raw: raw HTML in LLM output is NOT rendered (security §6). */}
                        <ReactMarkdown>{chunk.text}</ReactMarkdown>
                      </div>
                      {chunk.citations.length > 0 ? (
                        <ul className="mt-3 space-y-1 border-l border-rule pl-4">
                          {chunk.citations.map((citation) => (
                            <li
                              key={citation.marker}
                              className="text-xs text-ink-faint"
                            >
                              <span className="font-mono text-ink-soft">
                                {citation.marker}
                              </span>{" "}
                              {citation.url &&
                              /^https?:\/\//i.test(citation.url) ? (
                                <a
                                  href={citation.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-moss underline decoration-rule-strong underline-offset-2 hover:decoration-moss"
                                >
                                  {citation.domain || citation.url}
                                </a>
                              ) : (
                                <span>{citation.domain || "source"}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ))}
                </section>
              ))}
            </div>
          </>
        ) : sections.length ? (
          <>
            <p className="font-serif text-lg italic text-ink-soft">
              Drafting sections…
            </p>
            <div className="mt-6 space-y-6">
              {sections.map((section) => (
                <article key={section.sectionId} className="border-t border-rule pt-4">
                  <div className="flex items-baseline justify-between">
                    <p className="font-serif text-base font-medium text-ink">
                      {section.title}
                    </p>
                    <span className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
                      {section.status === "done" ? "done" : "writing"}
                    </span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">
                    {section.partialText || "Gathering material for this section…"}
                  </p>
                </article>
              ))}
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center">
            <p className="max-w-xs text-center font-serif text-lg italic leading-relaxed text-ink-faint">
              The finished report takes shape here, section by section.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
