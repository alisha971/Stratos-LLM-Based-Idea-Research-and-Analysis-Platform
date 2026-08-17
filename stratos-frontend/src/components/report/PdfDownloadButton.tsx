"use client";

type PdfDownloadButtonProps = {
  onDownload: () => void;
  disabled?: boolean;
};

export function PdfDownloadButton({
  onDownload,
  disabled = false,
}: PdfDownloadButtonProps) {
  return (
    <button
      onClick={onDownload}
      disabled={disabled}
      className="border border-rule-strong px-3 py-1.5 text-xs text-ink hover:bg-paper-sunken disabled:cursor-not-allowed disabled:opacity-40"
      title="Download PDF"
    >
      Download PDF
    </button>
  );
}
