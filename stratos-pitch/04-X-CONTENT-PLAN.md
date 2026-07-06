# 04 — X (Twitter) Content Plan: Posts, Drafts & Schedule

> A ready-to-run 6-week posting calendar for launching Stratos on X, with actual draft posts you can edit and ship. Voice rules first, then the calendar, then the draft bank. Post from the **founder's personal account** — personal accounts outperform brand accounts pre-launch by a wide margin.

## Voice rules (apply to every post)

1. Show, don't claim: screenshot/video/number in ≥ 70% of posts. Text-only hot takes are for accounts that already have audiences.
2. Specifics beat adjectives: "9 workers, 14 sources, 96% verified-citation rate" > "powerful AI system".
3. One idea per post. Threads only when each tweet stands alone.
4. Honest > hype: posts admitting a failure or a limitation consistently outperform victory laps for small accounts — they're rarer and more credible.
5. End engagement-bait-free: a genuine question or a link, never "like if you agree".
6. Cadence: 1 post/day minimum during this plan (30 min/day, per the GTM doc's build-in-public habit). Best windows for a global/US audience from India: 6:30–8:30 PM IST (morning US-East) and 10:30 PM IST; experiment and check analytics weekly.

## The 6-week calendar

**Weeks 1–2 = building in public (pre-launch) · Week 3 = launch week · Weeks 4–6 = content engine.** Adjust to your actual dev timeline (fast-ship: weeks 1–2 map to the 14 days; premium: stretch weeks 1–2 across Stages 1–4).

### Week 1 — Introduce the problem & the build (drafts 1–7)

| Day | Post | Format |
|---|---|---|
| Mon | #1 The origin story | text + 1 screenshot |
| Tue | #2 The problem, quantified | text |
| Wed | #3 Architecture reveal | diagram image |
| Thu | #4 Build detail: citations | code/output screenshot |
| Fri | #5 First full pipeline run | screen recording |
| Sat | #6 A failure post | screenshot of the bug |
| Sun | #7 Sample report giveaway #1 | PDF link |

### Week 2 — Deepen + collect waitlist (drafts 8–14)

Mon: streaming UI demo clip · Tue: "how we stop hallucinations" (auditor explainer) · Wed: sample report giveaway #2 (reply-to-get format) · Thu: trend-momentum chart screenshot ("search interest in X is up 2.4×") · Fri: cost-per-report economics post · Sat: waitlist milestone + what's left before launch · Sun: quote-tweet a Deep Research take with your positioning ("chat answers vs decision documents").

### Week 3 — Launch week (drafts 15–19, coordinate with GTM doc §4)

| Day | Post |
|---|---|
| Mon | #15 "We're live" + demo video + link (pin this) |
| Tue | Launch-day numbers, honest ("47 reports generated in 24h, 3 crashes, all fixed — here's what broke") |
| Wed | Product Hunt day: PH link + ask for feedback (not votes) |
| Thu | Show HN cross-post + the technical write-up as a thread |
| Fri | Best user-generated report of the week (with permission) + testimonial |
| Sat/Sun | Reply-guy days: answer every comment/DM; RT/quote user posts |

### Weeks 4–6 — The content engine (repeatable formats)

Rotate these five formats, one per weekday (this is the GTM doc's "daily content engine", scheduled):

1. **Market Monday** — run Stratos on a trending topic; post 3 surprising cited findings + free PDF link. (Your best format: product demo + SEO seed + lead-gen in one.)
2. **Teardown Tuesday** — one pipeline internal explained in 4–6 tweets (evidence ranker, SSRF guard, consent gate…). Builds the technical-credibility audience that YC founders and investors lurk in.
3. **Win Wednesday** — user story, metric milestone, or revenue update (₹/$ transparency posts travel far).
4. **Threads Thursday** — longer thread: lessons, numbers, mistakes ("6 things I learned making an LLM cite its sources").
5. **Free-report Friday** — "Reply with your idea, first 5 get a free report" (engagement + user pipeline; cap it to protect your budget).

## Draft bank (edit the brackets, keep the shape)

**#1 origin:**
> I kept seeing founders pay $2,000+ for market research reports — or paste their idea into ChatGPT and get confident answers with zero sources.
>
> So I'm building Stratos: type an idea, get a fully-cited market research PDF in ~10 minutes.
>
> Building it in public. Day 1 👇 [screenshot]

**#3 architecture:**
> Under the hood, Stratos is 9 workers in a pipeline:
>
> interview → outline → research (14 sources) → trends → competitors → write (with citation checks) → assemble → PDF
>
> Not a wrapper — the LLM is one component. The system's job is making sure it can't lie. [diagram]

**#4 citations:**
> My favorite rule in the codebase: if the AI writes a claim and the auditor can't trace it to a source, the sentence gets DELETED.
>
> A shorter honest report beats a longer lying one.
>
> Here's what the auditor caught today 👇 [screenshot]

**#6 failure:**
> Today's bug: my scraper trusted every URL the search engine returned. One redirect chain later it was happily requesting internal addresses.
>
> If you're building anything that fetches URLs from the internet: SSRF guards are not optional. [screenshot]

**#7 giveaway:**
> I ran Stratos on "[topical market]" — 10 minutes, [N] sources, every claim linked.
>
> 3 things that surprised me:
> 1. [finding + source]
> 2. [finding + source]
> 3. [finding + source]
>
> Full PDF, free: [link]

**#15 launch:**
> Stratos is live. 🚀
>
> Type your startup idea → get an investor-grade market research report — market size, competitors, trends, risks — every claim cited to a real source. ~10 minutes.
>
> Free tier: 2 reports/month. Built solo in [N] weeks.
>
> [demo video] [link]

## Weekly 15-minute review (Sundays)

Check X analytics: top post (make more of that format), worst post (make less), profile-visit→follow rate, and — the number that matters — **link clicks → signups** (tag links `?ref=x`). Followers are vanity; signups are the metric. Adjust next week's mix accordingly.

## What not to post

- Engagement farming ("RT if you think AI will change everything") — attracts an audience that will never pay.
- Roadmap promises with dates you'll miss publicly.
- Anything about specific users' ideas without explicit permission (their ideas are confidential — see security doc §8; this is trust-fatal if violated).
- Competitor trash talk — position, don't punch.
