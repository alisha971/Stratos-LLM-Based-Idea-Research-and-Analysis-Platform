# 10 — India Indie-Hacker Playbook

> The solo, low-budget, India-based path from this repo to your first paying customer. Assumes: you're one person, you have a laptop and ~₹5,000/month to spend, you may be a student or have a day job, and you've never launched anything. Everything is broken into weeks with tiny daily steps. Where a step is technical, it points at docs 03–08 — you don't need to reinvent anything.
>
> Total budget to first revenue: **₹3,000–6,000/month** (~$35–70). Timeline: **8 weeks** part-time.

---

## Week 0 — Validate before you build (yes, before finishing the code)

The code is ~70% done, which is exactly when indie hackers waste months polishing something nobody wants. Spend one week proving demand:

1. **Day 1–2:** Run the pipeline locally (doc 07 Part 1) for 3 ideas from friends. You now have 3 real PDFs. These PDFs are your entire marketing department for the next month.
2. **Day 3–5:** Message 25 people — startup WhatsApp groups, college e-cell alumni, LinkedIn connections who post about their startup, founders on X with <5k followers (they reply). Script:
   > "Hey — I built a tool that turns a startup idea into a cited market-research report (like a mini analyst report) in ~10 minutes. Reply with your idea and I'll send you one free. Only ask: 5 minutes of honest feedback."
3. **Day 6–7:** Deliver the reports (run them manually), collect feedback, and ask THE question: *"If this existed as a website, would you pay ₹999/month for 10 reports? If not ₹999, what?"*

**Go/no-go:** at least 5 of 25 say they'd pay (or, better, someone asks "can I pay you right now?"). If fewer — change the audience (try consultants/MBA students) before changing the product. Do not skip to Week 1 on hope.

## Weeks 1–3 — Finish the product (part-time coding)

Follow docs 03 and 04 top-to-bottom. If you're not a strong developer, this is exactly what AI coding agents are for — feed them one numbered task at a time along with doc 05; each task has its own "how to verify" so you can check the work without reading every line.

Priority order if time is short (this is the minimum sellable product):
1. Backend B1 (contract fixes) + B2 (report/PDF endpoints) — the product is worthless until the PDF reaches the user.
2. Frontend F1 + F2 — real streaming report + working download button.
3. Backend B4 + Frontend F3 — Google login (you can't have customers without accounts).
4. Backend B3, B6, B7 — env hygiene, R2, Docker (needed to deploy).
5. Everything else (rate limits, quotas, CI) — before charging strangers, per doc 08.

Ship discipline: every evening, run the smoke script (B8.1). If it's red, fixing it is tomorrow's first task.

Meanwhile, 30 min/day: post progress on X/LinkedIn (doc 09 §2.2) and keep delivering manual free reports — target one per day. Each recipient goes into a spreadsheet: name, idea, feedback, "would pay?".

## Week 4 — Deploy

Follow doc 07 click-by-click. India-specific choices:

- **Hosting regions:** pick Singapore (`ap-southeast-1`) or Mumbai where offered (Railway/Neon/Vercel all have nearby regions) — snappier for Indian users.
- **Domain:** `.in` domains are ~₹500–700/yr; `.com` ~₹1,000. Buy on Cloudflare or GoDaddy India (pay in INR, no forex markup).
- **Card for services:** most Indian credit/debit cards work for Railway/Vercel/Groq; enable "international transactions" in your banking app. If a card is refused, Niyo/Fi/Jupiter virtual international cards usually work.
- **Monthly infra bill at this stage:** Railway ~$10 + Redis $5 + domain amortized ≈ **₹1,500–2,500/month**. SerpAPI stays on free tier until you have users (or switch to Serper.dev's cheap credits — doc 06 §2.2 — which for India-budget purposes is the right call almost immediately).

## Week 5 — Payments, India edition

### Option A (start here): Razorpay Payment Links — zero code

Before building the full billing integration (doc 08), start collecting money manually:

1. Sign up at `razorpay.com` → KYC needs PAN + bank account (individual/proprietor is fine to start; activation typically takes a few days).
2. Create **Payment Links** for ₹999 (Starter) and ₹2,999 (Pro). UPI, cards, netbanking all work.
3. On your pricing page, the "Upgrade" button opens the payment link. When someone pays, Razorpay emails you → you manually set `users.plan='starter'` in the Neon console (SQL: `UPDATE users SET plan='starter', reports_used_this_month=0 WHERE email='...';`).
4. This is ugly and it does not scale. **It does not need to.** At <20 customers, manual is fine and you learn who your buyers are because you literally touch every sale.

### Option B (at ~20 customers): Razorpay Subscriptions API

Implement doc 08 §3 with Razorpay instead of Stripe: create Plans in the dashboard, `POST /billing/checkout` creates a Subscription and returns its short URL, webhook `subscription.activated` / `subscription.cancelled` flips `users.plan`. Same code shape, different SDK (`pip install razorpay`).

### Pricing for India + global

- Indian customers: ₹999/₹2,999 via Razorpay (UPI is the #1 payment method — never launch India-first without it).
- Global customers: add Stripe later, or skip entity headaches entirely with **Lemon Squeezy / Paddle / Dodo Payments** (merchant of record — they handle US/EU sales tax and pay you out; they take ~5% but remove enormous admin).

### Tax reality check (India)

- GST registration is mandatory once turnover crosses ₹20 lakh/yr (services), **or earlier if you sell inter-state/export via some MoR arrangements** — but as a practical matter: below a few lakh in revenue, register as it becomes needed; talk to a CA for ~₹2,000 when the first real money arrives (find one on UrbanClap/referrals). Exports of services (foreign customers) are zero-rated under GST with an LUT — again, CA territory. Don't pre-optimize taxes at ₹0 revenue.
- Keep it simple: one separate savings account for all Stratos money; log every income/expense in one spreadsheet from day one.

## Week 6 — Launch (India sequencing)

Follow doc 09 §4, with local additions and this order:

1. **Soft launch to your feedback list** (the spreadsheet from weeks 0–3 — these people already like you). Offer: "First month of Starter free, forever-20%-off as a founding user."
2. **India communities first** (warmer, kinder to first-timers): Indie Hackers India / buildinpublic-India on X (`#buildinpublic` + tag @IndieHackersIN-type communities), relevant subreddits (r/StartUpIndia, r/IndianStartups — read self-promo rules, post a useful artifact not a link), local founder WhatsApp/Telegram/Discord groups, college E-Cell networks (mail your alma mater's E-Cell offering free reports for their incubated teams).
3. **Product Hunt + Show HN** (global) once the India soft-launch surfaced and fixed the embarrassing bugs.
4. **The daily content engine (your unfair advantage, ₹0):** each day, generate one report on a trending Indian startup topic ("quick-commerce dark stores", "UPI credit lines", "D2C ayurveda brands"), post 3 surprising cited findings as an X/LinkedIn thread with 2 screenshots, end with "full PDF free → link". This is simultaneously product demo, SEO seed, and lead gen. 30 minutes/day, compounding.

## Weeks 7–8 — First revenue and the loop

- **Founding-user offer:** 50% off for life for the first 20 customers (₹499/mo). Announce publicly with a countdown of remaining seats — scarcity that's actually true.
- **Talk to every single paying customer** on a 15-min call or WhatsApp. Ask: what did you use the report for? What section did you skip? Who else needs this? (That last answer is your next 10 customers.)
- **Run the doc 09 §6 metric loop weekly.** Your numbers will be tiny; the habit is the point.
- **Milestones to celebrate publicly** (each is a build-in-public post that brings more users): first paying customer → first ₹10k month → first international customer → first ₹1L month.

## Realistic money math (so you don't quit at the wrong time)

| Stage | Customers | MRR | Note |
|---|---|---|---|
| Month 2 | 5 founding @ ₹499 | ₹2,500 | Covers infra. You are profitable. Seriously. |
| Month 4 | 20 mixed | ₹15–20k | Quit-your-tuition-fees money; still part-time |
| Month 6 | 50 + a few Pro/global | ₹50–80k | Comparable to a junior salary; consider full-time |
| Month 12 | 150+ with SEO flywheel | ₹2L+ | Now the YC/funding conversation (doc 09 §9) is real — with revenue proof |

Churn will be high (users finish researching and leave). Fight it with: the pay-per-report tier (₹499 one-time — impulse-friendly), the weekly public-report SEO engine, and later "market monitoring" (the trend worker re-running monthly on their saved topics — a genuinely sticky feature the codebase is already 80% built for).

## Traps that kill India indie hackers (avoid explicitly)

1. **Building for weeks 1–3 without doing Week 0.** The #1 killer. The DMs are uncomfortable; send them anyway.
2. **Pricing in fear** (₹99/mo). Your marginal cost is ~₹15/report and the alternative costs the customer days. ₹999 is cheap. Underpricing also attracts the worst customers.
3. **Buying ads before ₹50k MRR.** Every rupee before that goes to infra and nothing else.
4. **Feature-building instead of distribution** after launch. Post-launch, the split is 20% code / 80% talking to users and creating content. The competitor worker, embeddings, deep-dive — none of it matters until 50 people pay.
5. **Waiting for perfect legal/tax setup.** Payment link + savings account + spreadsheet is compliant enough to start; hire the CA when there's something to count.
6. **Silent grinding.** In public, weekly, even when numbers are embarrassing. The Indian build-in-public community is unusually supportive and is itself full of your target customers.

## Your single next action

If the smoke test (doc 07 Part 1 step 7) has never passed on your machine: that's today's task. If it has: send the first 5 Week-0 DMs right now, before touching any more code.
