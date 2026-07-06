"use client";

type PdfDownloadButtonProps = {
  onDownload: () => void;
};

export function PdfDownloadButton({ onDownload }: PdfDownloadButtonProps) {
  return (
    <button
      onClick={onDownload}
      className="rounded-lg border border-zinc-600 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
      title="Download PDF"
    >
      Download PDF
    </button>
  );
}
