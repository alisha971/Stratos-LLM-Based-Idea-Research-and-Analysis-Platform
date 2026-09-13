import type { Metadata } from "next";
import Link from "next/link";

import { Logo, LogoMark } from "@/components/brand/Logo";

export const metadata: Metadata = {
  title: "Stratos — Should you build it, or let it go?",
  description:
    "You have an idea you can't stop thinking about, and no straight answer about whether it's worth your next six months. Stratos asks a few sharp questions, reads the live web for and against it, and hands you a cited verdict — build it, reshape it, or walk away. Free while in beta.",
};

const audiences = [
  {
    who: "Indie hackers",
    pain: "“I have six ideas and one free weekend. I don't know which one deserves it.”",
    got: "A case for each: where demand is real, who already owns the space, and the one shift that would make yours worth shipping.",
  },
  {
    who: "Students & researchers",
    pain: "“My advisor asked if this has been done before. I've been tab-hopping for two days.”",
    got: "A cited landscape of what exists, what contradicts your premise, and an honest list of what nobody has answered yet — your gap, in writing.",
  },
  {
    who: "Product managers",
    pain: "“I have to defend this bet on Thursday and all I have is a gut feeling.”",
    got: "A brief that argues both sides, so you walk in with the counter-argument already answered instead of hearing it first from your VP.",
  },
  {
    who: "Founders & career-switchers",
    pain: "“Everyone I ask says it sounds great. Nobody tells me what would kill it.”",
    got: "The strongest case against your idea, sourced — and a plain verdict on whether the case for it still wins.",
  },
];

const examples = [
  {
    idea: "“A meal-prep app for medical residents.”",
    verdict:
      "Pivot — the audience is real but too small to price for. Same product, adjacent audience, and the numbers work.",
  },
  {
    idea: "“An AI note-taker for therapists.”",
    verdict:
      "Don't build it as scoped — compliance load and incumbent distribution point the same way, and here is the evidence behind each.",
  },
  {
    idea: "“A thesis on gig-worker credit scoring in India.”",
    verdict:
      "Go — three papers circle the question and none answer it. That unanswered piece is your contribution.",
  },
];

const contrast = [
  {
    label: "Asking a chatbot",
    line: "It agrees with you. Ask the same idea twice, phrased two ways, and you get two confident answers — neither one shows its evidence.",
  },
  {
    label: "Scoring tools",
    line: "A number out of 100 from one paragraph of input. You can't argue with a score, and you can't take it to anyone.",
  },
  {
    label: "A weekend of your own research",
    line: "You find what you were hoping to find. Nobody spends Saturday hunting for the reason their own idea fails.",
  },
];

const steps = [
  {
    n: "01",
    title: "Tell it what you're building",
    body: "One sentence is plenty. It asks you two or three pointed questions back — so it judges your actual idea, not a guess at it.",
  },
  {
    n: "02",
    title: "It looks for the reasons you're wrong",
    body: "Live search, trend data, competitor scans — deliberately hunting for evidence against you, not just for you. You watch it happen, and every claim keeps its source.",
  },
  {
    n: "03",
    title: "You get a verdict you can argue with",
    body: "Build, reshape, or walk away — written out like a judge's opinion: which evidence won, why, and the exact thing that would flip the answer.",
  },
  {
    n: "04",
    title: "It tells you what it couldn't find out",
    body: "No confident filler. Whatever the research couldn't settle is listed plainly, so you know which calls are still yours — in a report you can export and send on.",
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
              For the idea you keep coming back to
            </p>
            <h1 className="mt-6 max-w-2xl font-serif text-5xl font-medium leading-[1.08] tracking-tight sm:text-6xl">
              Build it, reshape it, or{" "}
              <em className="text-moss">let it go</em>?
            </h1>
            <p className="mt-8 max-w-xl text-lg leading-relaxed text-ink-soft">
              You already have the idea. What you don&rsquo;t have is a straight
              answer about whether it deserves your next six months. Give
              Stratos one sentence. It asks what you actually mean, reads the
              live web for you and against you, and hands back a cited verdict
              you can defend — about ten minutes, while you watch it work.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-5">
              <Link
                href="/login"
                className="bg-moss px-6 py-3 text-sm font-medium text-paper shadow-lift hover:bg-moss-deep"
              >
                Settle my idea
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

        {/* Who it's for — the pain, in their words */}
        <section className="border-t border-rule-strong py-14">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-ink-faint">
            You&rsquo;ve probably said one of these out loud
          </p>
          <div className="mt-8 grid gap-x-10 gap-y-8 sm:grid-cols-2">
            {audiences.map((a) => (
              <div key={a.who} className="border-t border-rule pt-5">
                <h2 className="font-mono text-xs uppercase tracking-[0.16em] text-moss">
                  {a.who}
                </h2>
                <p className="mt-3 font-serif text-lg italic leading-snug text-ink">
                  {a.pain}
                </p>
                <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                  {a.got}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Why not the usual route */}
        <section className="border-t border-rule-strong py-14">
          <h2 className="max-w-2xl font-serif text-3xl font-medium leading-tight">
            You&rsquo;re not stuck for lack of effort. You&rsquo;re stuck
            because nothing you&rsquo;ve tried was willing to disagree with you.
          </h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-3">
            {contrast.map((c) => (
              <div key={c.label} className="border-t border-rule pt-4">
                <h3 className="font-mono text-xs uppercase tracking-[0.16em] text-ink-faint">
                  {c.label}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-ink-soft">
                  {c.line}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-10 max-w-2xl text-base leading-relaxed text-ink-soft">
            Stratos runs a pass whose only job is to build the case against your
            idea, tags every source with the side it argues for, and then weighs
            the two out in the open. That&rsquo;s why the answer is something
            you can push back on at a specific step — instead of a verdict you
            either swallow whole or ignore.
          </p>
        </section>

        {/* Examples */}
        <section className="border-t border-rule-strong py-14">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-ink-faint">
            What people bring it — and what they walk out with
          </p>
          <div className="mt-8 divide-y divide-rule border-y border-rule">
            {examples.map((e) => (
              <div
                key={e.idea}
                className="grid gap-2 py-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:gap-10"
              >
                <p className="font-serif text-lg italic leading-snug text-ink">
                  {e.idea}
                </p>
                <p className="text-sm leading-relaxed text-ink-soft">
                  {e.verdict}
                </p>
              </div>
            ))}
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
            From an actual verdict
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
                &ldquo;Go — with one condition. Demand is real: the Indian D2C
                skincare market reached an estimated $1.2B in 2025, growing at
                roughly 25% annually [3][7]. Against you: three funded
                incumbents already own tier-1 distribution [2][5]. This verdict
                flips unless you start in the men&rsquo;s segment, where
                incumbents are weakest [6].&rdquo;
              </blockquote>
              <figcaption className="mt-4 text-sm text-ink-faint">
                Every bracket links to the source it came from. Every verdict
                names what would change it.
              </figcaption>
            </figure>
          </div>
        </section>

        {/* Closing call */}
        <section className="border-t border-rule-strong py-14">
          <h2 className="max-w-xl font-serif text-3xl font-medium leading-tight">
            Stop rehearsing the idea in your head. Put it in writing and find
            out.
          </h2>
          <div className="mt-8 flex flex-wrap items-center gap-5">
            <Link
              href="/login"
              className="bg-moss px-6 py-3 text-sm font-medium text-paper shadow-lift hover:bg-moss-deep"
            >
              Settle my idea
            </Link>
            <span className="text-sm text-ink-faint">
              One sentence to start. Ten minutes to a verdict.
            </span>
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
