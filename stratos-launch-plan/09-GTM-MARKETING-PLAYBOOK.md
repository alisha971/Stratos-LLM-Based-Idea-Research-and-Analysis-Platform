# 09 — GTM & Marketing Playbook (Non-Technical Cofounder's Manual)

> Everything outside the code: positioning, audience, launch, channels, sales, and legal basics. Written so a business cofounder with zero engineering background can execute it alone. The only technical dependency: the product must pass the launch gate in doc 08 §5 before section 5 of this doc (public launch) begins. Everything before that can start **today**, in parallel with development.

---

## 1. Positioning

### 1.1 One-liner

> **Stratos turns your startup idea into an investor-grade, fully-cited market research report in 10 minutes.**

### 1.2 The problem, in the customer's words

- "I'm pitching next week and I have no TAM/competition slide."
- "Gartner/CB Insights reports cost $2,000–15,000 and don't cover my niche."
- "ChatGPT gives me confident answers with no sources. I can't put that in front of an investor or a client."

### 1.3 Differentiation (memorize this)

| vs. | Stratos wins because |
|---|---|
| ChatGPT / Claude directly | Every claim is **cited to a real, clickable source** (search results, news, GDELT, arXiv); structured multi-section report; a PDF you can attach to a deck |
| Analyst firms (Gartner, CBI) | 100–1000× cheaper, covers any niche, on demand |
| Freelance researchers (Upwork) | Minutes not weeks; $19 not $500; consistent structure |
| Free googling | The clarification interview forces the user to sharpen the question, then does 10+ searches and synthesis they'd never do manually |

The moat at this stage is not technology — it's **speed of iteration + the citations trust story + owning a niche audience**. Say "cited" in every sentence of marketing.

### 1.4 Target segments, in priority order

1. **Pre-seed/seed founders** writing decks (feel the pain weekly; hang out in public: Twitter/X, LinkedIn, YC co-founder matching, Discord/Slack communities).
2. **Freelance consultants & fractional CMOs/strategists** (will pay Pro; a report is a deliverable they resell inside $5k engagements).
3. **University entrepreneurship programs & MBA students** (volume, price-sensitive, great for word-of-mouth; sell Starter or campus deals).
4. **Micro-VC / accelerator analysts** (screening dozens of ideas; later target with a team plan).

Do NOT market to "everyone doing research." Pick segment 1 for the first 90 days.

---

## 2. Pre-launch (start now, ~3 weeks parallel to dev)

### 2.1 Assets to produce (checklist)

- [ ] Name/domain/logo (a wordmark from a font is fine; do not spend >1 day).
- [ ] 3 **sample reports** on ideas your audience recognizes ("AI agents for dental clinics", "D2C protein coffee in India", "carbon accounting for SMBs") — these are your #1 sales asset. Host as public PDFs.
- [ ] 45-second demo video: screen recording of idea → clarification → live sections streaming → PDF. Record with Loom or OBS. The "sections appearing live" moment is the wow — center it.
- [ ] Landing page (built in frontend task F4.2) with waitlist email capture pre-launch (a simple Tally/Formspark form is fine before real auth exists).
- [ ] Social accounts: X/Twitter + LinkedIn under the founder's personal name (personal accounts outperform brand accounts at this stage).

### 2.2 Build-in-public cadence (founder-led, 30 min/day)

- 3 posts/week on X + LinkedIn: progress screenshots, one juicy insight from a sample report ("We analyzed the pet-insurance market in 10 min — here are 3 things that surprised us, sources linked"), and one behind-the-scenes ("how we force the AI to cite every claim").
- Every post ends with the waitlist link.
- Target before launch day: 300+ waitlist emails. If you're far below, your positioning or audience is off — fix that **before** launching, not after.

### 2.3 Manual validation (do not skip)

DM 20 founders from your network: "Send me your idea, I'll send you a free market report in return for 15 minutes of feedback." Run their ideas through the product yourself. You will learn: which sections they actually read, what they'd pay, what's embarrassing. Fix the embarrassing things. Collect 5 quotable testimonials (ask permission).

---

## 3. Pricing & packaging (business owner's view)

The engineering side is doc 08 §1. Your decisions:

- Lead with **annual-discount toggle off** at launch (monthly only) — simpler, and you don't yet deserve annual commitments.
- Free tier exists for virality (2 reports, watermarked footer). Watch abuse; if people cycle Google accounts, that's a good problem — tighten later.
- **Money-back guarantee, 7 days, no questions.** Removes purchase anxiety, costs you almost nothing at >90% margins, and refund requests are the best interview pipeline.

---

## 4. The launch sequence (one week, in order)

**Day 1 — Soft launch to the waitlist.** Email: "You're in. First 100 people get Starter free for a month, code EARLYBIRD." Watch Sentry + completion rate all day. Fix breakages silently.

**Day 3 — Product Hunt.**
- Prepare 5 days ahead: gallery images (report screenshots), the demo video, first-comment text telling the origin story + a free sample report link.
- Launch 12:01 AM Pacific. Founder answers every comment within 15 min, all day.
- Ask your waitlist (in the Day 1 email's PS) to "come say hi on PH Thursday" — never ask directly for upvotes.

**Day 4 — Hacker News "Show HN".**
- Title: `Show HN: Stratos – cited market-research reports from an idea, in ~10 minutes`.
- First comment: honest technical write-up — the worker pipeline, how citations are validated, what it's bad at. HN rewards candor and punishes marketing-speak. Link a sample report, not the pricing page.

**Day 5–7 — Communities.** Reddit (r/startups, r/Entrepreneur, r/SideProject, r/indiehackers), relevant Discords/Slacks. Format that works: post a **useful artifact** ("I generated a market analysis of [topic the sub cares about] — full PDF here") with the tool mentioned once at the end. Never post bare links; read each community's self-promo rules first.

**Ongoing spike handling:** the circuit breaker (doc 08 §4.3) protects the budget. If you hit capacity on launch day, that's a screenshot-worthy tweet, not a crisis.

---

## 5. Post-launch channels (rank by effort-to-payoff at this stage)

1. **Programmatic SEO (best long-term asset).** Publish one generated report per week as a public HTML page: "Market Research: {industry} {year}" — each is a long-tail SEO magnet ("plant-based pet food market size") with a CTA to generate a custom version. 52 pages/year compounds. Requires a small eng task (public report pages) — schedule it ~month 2.
2. **Founder-led social** (continue the §2.2 cadence forever; it's free).
3. **Partnerships:** accelerators + university e-cells — offer free Pro for their cohort in exchange for a mention in their onboarding docs. One email template, 50 sends, ~5 yeses.
4. **Affiliates for consultants** (month 3+): 20% recurring for 12 months; consultants who resell reports become a sales force.
5. **Paid ads:** do NOT touch before $2k MRR and knowing your conversion rate. Then start with $10/day on Google Search for "market research report generator"-type keywords only.

---

## 6. Metrics & iteration loop

Track weekly, in a spreadsheet, from the `/admin/stats` endpoint (doc 08 §4.5) + Stripe:

| Metric | Healthy early signal |
|---|---|
| Visitor → signup | ≥ 8% |
| Signup → first completed report | ≥ 60% (below = onboarding/pipeline problem) |
| Free → paid conversion | ≥ 3–5% |
| MRR week-over-week | growing at all |
| Churn (monthly) | < 10% (report tools skew high-churn — fight it with the SEO/report-library retention hooks) |
| Refund rate | < 5% |

**The weekly loop:** pick the worst number → form one hypothesis → ship one change (copy, price, onboarding step, report quality) → re-measure. One change per week, no more.

Pricing experiments (only after 20+ paying customers): test $29 Starter with new signups only; test the $9 pay-per-report; never change existing customers' prices upward.

---

## 7. Sales motion for the bigger fish (consultants, VCs, programs)

- Source: LinkedIn search "market research" + "fractional" / accelerator program managers. 10 personalized DMs/week.
- The pitch is a **free custom report on their current client's/portfolio's space** ("Here's what Stratos produced on vertical-SaaS-for-logistics in 10 minutes — sources included"). The artifact does the selling.
- Close on Pro or a simple 5-seat "team" invoice (Stripe payment link; don't build team features yet — shared login is fine at this stage).

---

## 8. Legal & admin minimum

- [ ] **Entity:** US Delaware C-Corp via Stripe Atlas/Clerky if raising US VC; Indian Pvt Ltd if staying India-first (doc 10 §6); LLC/sole-prop is fine pre-revenue. Don't let this block launch — many founders incorporate after first revenue.
- [ ] **Terms of Service + Privacy Policy:** generate drafts from a reputable template service (Termly, GetTerms, or a lawyer friend), covering: AI-generated content disclaimer ("reports are AI-generated research aids, not professional advice"), data handling (Google login data, ideas submitted, third-party processors: Groq, SerpAPI, Google), refunds, account deletion. Link in the footer. Have a lawyer review once revenue justifies it.
- [ ] **AI content disclaimer inside every PDF** (one footer line — small eng task).
- [ ] Taxes on SaaS sales: Stripe Tax (toggle in dashboard) or a merchant-of-record (Paddle/Lemon Squeezy) if global sales-tax handling scares you. India GST specifics: doc 10 §6.
- [ ] A `founders@yourdomain.com` inbox (Cloudflare Email Routing is free) answered daily. Early support IS marketing.

---

## 9. YC application angle (if you go that route)

- **The narrative:** "Market research is a $80B+ industry priced for enterprises. We make analyst-grade, fully-cited research instant and $19. Started with founders writing decks; expanding to the consultants and analysts who bill research at $200/hour."
- What YC wants to see: launch first, weekly growth chart (even small), retention proof, founder velocity (this repo's commit history is your evidence).
- The demo IS the application: idea → cited PDF live in minutes is a strong 60-second demo. Practice it until it never fails (that's the doc 08 launch-gate discipline paying off).
- Expansion story for the "how big can this be" question: report generation → continuous market monitoring (the trend worker already exists) → the system-of-record for market intelligence at every startup and fund.
