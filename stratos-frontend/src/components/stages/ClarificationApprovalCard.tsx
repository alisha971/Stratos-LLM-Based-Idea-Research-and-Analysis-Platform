type ClarificationApprovalCardProps = {
  summary: string;
  onEdit: () => void;
  onStartResearch: () => Promise<void> | void;
};

export function ClarificationApprovalCard({
  summary,
  onEdit,
  onStartResearch,
}: ClarificationApprovalCardProps) {
  return (
    <section className="rounded-2xl border border-zinc-700 bg-zinc-900 p-5">
      <h2 className="text-base font-semibold text-zinc-100">
        Clarification complete
      </h2>
      <p className="mt-3 text-sm leading-6 text-zinc-300">{summary}</p>
      <div className="mt-4 flex gap-2">
        <button
          onClick={onEdit}
          className="rounded-lg border border-zinc-600 px-4 py-2 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          Edit clarification
        </button>
        <button
          onClick={onStartResearch}
          className="rounded-lg bg-blue-500 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-400"
        >
          Start research
        </button>
      </div>
    </section>
  );
}
