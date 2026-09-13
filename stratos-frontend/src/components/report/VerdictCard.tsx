"use client";

import type { Verdict } from "@/lib/api/orchestratorClient";
import { useTypewriter } from "@/lib/hooks/useTypewriter";

type VerdictCardProps = {
  verdict: Verdict | null;
  unresolvedGaps: string[];
  // Whether a verdict is expected but hasn't arrived yet -- distinct from
  // "no verdict block at all" (nothing streaming yet). Reserves the slot
  // in a pending state so the block doesn't appear later and push the
  // body down mid-read (gap-closing plan Stage 5c).
  pending: boolean;
};

const VERDICT_LABEL: Record<Verdict["verdict"], string> = {
  build: "Build it",
  reshape: "Reshape it",
  walk_away: "Walk away",
};

function ProseBlock({ text }: { text: string }) {
  const shown = useTypewriter(text);
  return <p className="text-sm leading-relaxed text-ink-soft">{shown}</p>;
}

export function VerdictCard({ verdict, unresolvedGaps, pending }: VerdictCardProps) {
  if (!verdict) {
    if (!pending) return null;
    return (
      <section className="mb-10 border-b border-rule-strong pb-8">
        <p className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
          The verdict
        </p>
        <p className="mt-3 font-serif text-lg italic text-ink-faint">
          Weighing the evidence…
        </p>
      </section>
    );
  }

  const { payload } = verdict;

  return (
    <section className="mb-10 border-b border-rule-strong pb-8">
      <p className="font-mono text-[11px] uppercase tracking-wider text-ink-faint">
        The verdict — {VERDICT_LABEL[verdict.verdict]}
      </p>

      {verdict.holding ? (
        <h3 className="mt-3 font-serif text-2xl font-medium leading-snug text-ink">
          {verdict.holding}
        </h3>
      ) : null}

      {payload.case_for_prose ? (
        <div className="mt-6">
          <h4 className="font-mono text-xs uppercase tracking-wider text-moss">
            The case for
          </h4>
          <div className="mt-2">
            <ProseBlock text={payload.case_for_prose} />
          </div>
        </div>
      ) : null}

      {payload.case_against_prose ? (
        <div className="mt-6 border-l-2 border-rust pl-4">
          <h4 className="font-mono text-xs uppercase tracking-wider text-rust">
            The case against
          </h4>
          <div className="mt-2">
            <ProseBlock text={payload.case_against_prose} />
          </div>
        </div>
      ) : null}

      {payload.which_won ? (
        <div className="mt-6">
          <h4 className="font-mono text-xs uppercase tracking-wider text-ink-faint">
            Why one side won
          </h4>
          <div className="mt-2">
            <ProseBlock text={payload.which_won} />
          </div>
        </div>
      ) : null}

      {verdict.flip_condition ? (
        <div className="mt-6">
          <h4 className="font-mono text-xs uppercase tracking-wider text-ink-faint">
            What would flip it
          </h4>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            {verdict.flip_condition}
          </p>
        </div>
      ) : null}

      {unresolvedGaps.length > 0 ? (
        <div className="mt-6">
          <h4 className="font-mono text-xs uppercase tracking-wider text-ink-faint">
            What we couldn&rsquo;t settle
          </h4>
          <ul className="mt-2 space-y-1">
            {unresolvedGaps.map((gap) => (
              <li key={gap} className="text-sm leading-relaxed text-ink-soft">
                — {gap}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {verdict.confidence ? (
        <p className="mt-6 font-mono text-[11px] uppercase tracking-wider text-ink-faint">
          Confidence: {verdict.confidence}
        </p>
      ) : null}
    </section>
  );
}
