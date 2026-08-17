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
    <section className="border-l-2 border-moss bg-paper-raised p-5">
      <h2 className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
        Here&rsquo;s what I&rsquo;ll research
      </h2>
      <p className="mt-3 font-serif text-base leading-relaxed text-ink">
        {summary}
      </p>
      <div className="mt-5 flex items-baseline gap-4">
        <button
          onClick={onStartResearch}
          className="bg-moss px-5 py-2 text-sm text-paper hover:bg-moss-deep"
        >
          Start the research
        </button>
        <button
          onClick={onEdit}
          className="text-sm text-ink-soft underline decoration-rule-strong underline-offset-4 hover:text-ink"
        >
          Not quite — edit
        </button>
      </div>
    </section>
  );
}
