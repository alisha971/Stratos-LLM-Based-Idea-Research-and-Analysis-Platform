import type { Metadata } from "next";
import Link from "next/link";

import { Logo, LogoMark } from "@/components/brand/Logo";

export const metadata: Metadata = {
  title: "Stratos — Market research, written like a memo",
  description:
    "Stratos turns a one-line startup idea into a cited market research report in about ten minutes. Free while in beta.",
};

const steps = [
  {
    n: "01",
    title: "Say what you're building",
    body: "One sentence is plenty. Stratos asks two or three pointed questions to pin down the market you actually mean.",
  },
  {
    n: "02",
    title: "It goes and reads",
    body: "Live web search, trend data, competitor scans. You watch the work happen — every claim keeps its source.",
  },
  {
    n: "03",
    title: "You get a memo",
    body: "A structured report with inline citations, readable in the browser or exported as a PDF you'd hand to an investor.",
  },
];

/** Exploded isometric stack — the logo's strata, blown up as hero art. */
function StrataIllustration() {
  return (
    <svg
      viewBox="0 0 240 250"
      className="w-full max-w-[300px]"
      fill="none"
      aria-hidden="true"
    >
      {/* Ground shadow */}
      <ellipse cx="120" cy="238" rx="86" ry="10" fill="#211e19" opacity="0.08" />

      {/* Bottom stratum */}
      <path
        d="M120 128 220 183 120 238 20 183Z"
        fill="var(--paper-raised, #fbf9f3)"
        stroke="#aaa48f"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      {/* Middle stratum */}
      <path
        d="M120 92 220 147 120 202 20 147Z"
        fill="var(--paper-raised, #fbf9f3)"
        stroke="#211e19"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      {/* Contour hints on the middle layer */}
      <path
        d="M64 147c14-10 34-14 56-10s42 2 56-8"
        stroke="#d9d3c3"
        strokeWidth="1.1"
      />
      <path
        d="M78 160c12-7 26-9 42-6s34 1 46-7"
        stroke="#d9d3c3"
        strokeWidth="1.1"
      />

      {/* Top stratum — floats */}
      <g className="animate-[strata-float_5s_ease-in-out_infinite]">
        <path
          d="M120 34 220 89 120 144 20 89Z"
          fill="#245c3d"
          stroke="#1a4730"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        <path
          d="M66 89c16-11 36-15 54-11s40 3 54-9"
          stroke="#f5f2ea"
          strokeWidth="1.1"
          opacity="0.45"
        />
      </g>

      {/* Citation marker, pinned to the stack */}
      <g className="animate-[strata-float_5s_ease-in-out_infinite]">
        <line
          x1="188"
          y1="62"
          x2="212"
          y2="38"
          stroke="#9c3b2a"
          strokeWidth="1.1"
        />
        <rect x="204" y="20" width="30" height="20" fill="#f5f2ea" stroke="#9c3b2a" strokeWidth="1.1" />
        <text
          x="219"
          y="34"
          textAnchor="middle"
          fontSize="11"
          fill="#9c3b2a"
          fontFamily="var(--font-geist-mono), monospace"
        >
          [3]
        </text>
      </g>
    </svg>
  );
}

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-paper text-ink">
      <div className="mx-auto max-w-4xl px-6 sm:px-10">
        {/* Masthead */}
        <header className="flex items-center justify-between border-b border-rule-strong py-6">
          <Logo />
          <nav className="flex items-baseline gap-6 text-sm">
            <a
              href="/sample-report.pdf"
              className="text-ink-soft underline decoration-rule-strong underline-offset-4 hover:text-ink"
            >
              Sample report
            </a>
            <Link
              href="/login"
              className="bg-ink px-4 py-2 text-paper hover:bg-moss-deep"
            >
              Sign in
            </Link>
          </nav>
        </header>

        {/* Hero */}
        <section className="grid items-center gap-10 py-16 sm:py-20 md:grid-cols-[1fr_auto]">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-ink-faint">
              Market research, without the two weeks
            </p>
            <h1 className="mt-6 max-w-2xl font-serif text-5xl font-medium leading-[1.08] tracking-tight sm:text-6xl">
              A research analyst that shows its{" "}
              <em className="text-moss">sources</em>.
            </h1>
            <p className="mt-8 max-w-xl text-lg leading-relaxed text-ink-soft">
              Describe your startup idea in a sentence. Stratos clarifies what
              you mean, reads the live web, and writes a cited market report —
              market size, competitors, trends — in about ten minutes.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-5">
              <Link
                href="/login"
                className="bg-moss px-6 py-3 text-sm font-medium text-paper shadow-lift hover:bg-moss-deep"
              >
                Write my first report
              </Link>
              <span className="text-sm text-ink-faint">
                Free while in beta. No card.
              </span>
            </div>
          </div>
          <div className="hidden justify-center md:flex">
            <StrataIllustration />
          </div>
        </section>

        {/* How it works — ruled rows, not cards */}
        <section className="border-t border-rule-strong">
          {steps.map((step) => (
            <div
              key={step.n}
              className="grid gap-2 border-b border-rule py-8 sm:grid-cols-[80px_240px_1fr] sm:gap-8"
            >
              <span className="font-mono text-sm text-ink-faint">{step.n}</span>
              <h2 className="font-serif text-xl font-medium">{step.title}</h2>
              <p className="text-sm leading-relaxed text-ink-soft">
                {step.body}
              </p>
            </div>
          ))}
        </section>

        {/* Specimen — a stacked sheet of the actual output */}
        <section className="py-16">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-ink-faint">
            From an actual report
          </p>
          <div className="relative mt-8 max-w-2xl">
            {/* Sheets underneath — gives the document physical depth */}
            <div
              aria-hidden="true"
              className="absolute inset-0 translate-x-2.5 translate-y-2.5 rotate-[0.7deg] border border-rule bg-paper-raised"
            />
            <div
              aria-hidden="true"
              className="absolute inset-0 translate-x-1 translate-y-1 rotate-[-0.4deg] border border-rule bg-paper-raised"
            />
            <figure className="relative border border-rule-strong bg-paper-raised p-8 shadow-lift">
              <blockquote className="font-serif text-xl italic leading-relaxed text-ink">
                &ldquo;The Indian D2C skincare market reached an estimated $1.2B
                in 2025, growing at roughly 25% annually, driven primarily by
                tier-2 city adoption [3][7]. Incumbents remain weakest in the
                men&rsquo;s segment.&rdquo;
              </blockquote>
              <figcaption className="mt-4 text-sm text-ink-faint">
                Every bracket is a live link to the source it came from.
              </figcaption>
            </figure>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-rule-strong py-10 text-sm text-ink-faint">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-baseline sm:justify-between">
            <div className="flex items-start gap-3">
              <LogoMark className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" />
              <p className="max-w-md leading-relaxed">
                Reports are AI-written from public sources — verify anything
                you plan to put money behind. Data deletion on request during
                beta.
              </p>
            </div>
            <a
              href="mailto:beta@stratos.local"
              className="underline decoration-rule-strong underline-offset-4 hover:text-ink"
            >
              beta@stratos.local
            </a>
          </div>
        </footer>
      </div>
    </main>
  );
}
