const stages = [
  "Login",
  "Session Start",
  "Clarification",
  "Consent",
  "Outline",
  "Research",
  "Trend/Competitor (stubbed)",
  "Section Streaming (stubbed live-ready)",
  "Assembler/Export (stubbed)",
];

export function BackendSequenceMap() {
  return (
    <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
        Backend sequence aligned flow
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {stages.map((stage) => (
          <span
            key={stage}
            className="rounded-full border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300"
          >
            {stage}
          </span>
        ))}
      </div>
    </section>
  );
}
