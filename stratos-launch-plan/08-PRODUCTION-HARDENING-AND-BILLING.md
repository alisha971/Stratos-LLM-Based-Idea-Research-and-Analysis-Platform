# 08 — Production Hardening & Billing

> Do this **after** the app is deployed and working (doc 07) and **before** you take money from strangers. Billing is the centerpiece; the hardening items around it are what keep billing (and the product) trustworthy.

---

## 1. Pricing & plans (the model the code implements)

| Plan | Price | Reports/month | Target buyer |
|---|---|---|---|
| **Free** | $0 | 2 | Trial users; every report has a subtle "Generated with Stratos" footer |
| **Starter** | $19/mo (₹999 in India via Razorpay) | 10 | Indie founders, students, freelancers |
| **Pro** | $49/mo (₹2,999) | 40 + priority queue | Consultants, VC analysts, agencies |
| **Pay-per-report** (optional later) | $9 one-time | 1 | Impulse buyers who hate subscriptions |

Rationale: marginal cost per report is ≈$0.05–0.20 (doc 06 §3), the human alternative costs hours or thousands of dollars, and 10 reports for $19 anchors well against a single $2k analyst report. Start here; revisit after 20 paying customers (doc 09 §6 covers pricing experiments).

Plan limits live as constants in `app/config.py`:

```python
PLAN_LIMITS = {"free": 2, "starter": 10, "pro": 40}
```

The quota mechanics (columns on `users`, 402 on exceed, monthly reset) were built in backend task B5.2. This doc adds the way users **change** their plan: payments.

---

## 2. Choose the payment provider

- **Stripe** — global cards, best docs, hosted Checkout + Customer Portal. Requires a supported-country entity (US/EU/UK/SG etc. — India onboarding is restricted for new accounts; if you're an Indian solo founder without a foreign entity, use Razorpay, or use Paddle/Lemon Squeezy as a merchant-of-record which also handles global sales tax for you).
- **Razorpay** — Indian entity, UPI + cards + netbanking, subscriptions supported. Details for India in doc 10 §6.

The backend abstraction is identical either way: a `checkout` endpoint that returns a hosted-payment URL, and a `webhook` endpoint that flips `users.plan`. Implement one provider; the code structure below works for both.

## 3. Stripe integration (step by step)

### 3.1 Dashboard setup

1. `stripe.com` → create account → stay in **Test mode** (toggle, top right) until §3.5.
2. **Product catalog → Add product**: "Stratos Starter", recurring $19/month → note the **price ID** (`price_...`). Repeat for Pro $49.
3. **Developers → API keys**: copy the **secret key** (`sk_test_...`) → backend env `STRIPE_SECRET_KEY`. Store both price IDs as env `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PRO`.

### 3.2 Backend: checkout endpoint

`pip install stripe`, add to requirements. New file `app/api/billing.py`, mounted at `/billing`:

- `GET /billing/me` — returns `{plan, reports_used_this_month, limit, quota_reset_at}` for the JWT user.
- `POST /billing/checkout` — body `{"plan": "starter"|"pro"}`:
  1. Get-or-create a Stripe Customer for the user (store `stripe_customer_id` on the `users` row).
  2. `stripe.checkout.Session.create(mode="subscription", customer=..., line_items=[{"price": PRICE_ID, "quantity": 1}], success_url=f"{FRONTEND_ORIGIN}/billing?success=1", cancel_url=f"{FRONTEND_ORIGIN}/billing?canceled=1", client_reference_id=user_id)`.
  3. Return `{"checkout_url": session.url}`.

### 3.3 Backend: webhook

- `POST /billing/webhook` — **no JWT** (Stripe calls it), verify with `stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)`.
- Handle events:
  - `checkout.session.completed` → look up user by `client_reference_id` → set `plan` from the price ID, reset `reports_used_this_month = 0`, set `quota_reset_at` = now + 1 month.
  - `customer.subscription.updated` → sync plan on up/downgrades.
  - `customer.subscription.deleted` → set `plan = "free"`.
- Dashboard → **Developers → Webhooks → Add endpoint**: `https://api.yourdomain.com/billing/webhook`, select those three events → copy the **signing secret** (`whsec_...`) → env `STRIPE_WEBHOOK_SECRET`.
- Local testing: `stripe listen --forward-to localhost:8000/billing/webhook` (Stripe CLI) prints a temporary signing secret.

### 3.4 Cancel/manage: Customer Portal

Enable the no-code **Customer Portal** in Stripe settings; add `POST /billing/portal` returning `stripe.billing_portal.Session.create(customer=..., return_url=...).url`. Frontend "Manage subscription" button opens it. This gives you cancellations, card updates, and invoices for free.

### 3.5 Go live checklist

1. Complete Stripe business verification (identity, bank account).
2. Toggle to **Live mode**, recreate the two products, copy live keys/price IDs/webhook secret into Railway env, add the live webhook endpoint.
3. Buy your own Starter plan with a real card, verify the plan flips, then cancel via the portal and verify it reverts to free. Refund yourself from the dashboard.

### 3.6 Verification matrix (run all of these in test mode)

| Test | Expected |
|---|---|
| Checkout success | `users.plan = starter`, quota resets, banner on `/billing?success=1` |
| Checkout abandoned | plan unchanged |
| Webhook with bad signature | 400, no change |
| Subscription canceled | plan → free at period end |
| 3rd report on free plan | 402 + upgrade prompt in UI |
| 11th report on starter | 402 + upgrade prompt |

---

## 4. Hardening checklist (beyond what docs 03/04 built)

### 4.1 Security

- [ ] `JWT_SECRET` is 64+ random chars, only in secret managers; app refuses to boot in production with the default (backend B3.1).
- [ ] All pipeline/report/billing routes behind the JWT dependency with ownership checks (backend B4.2) — re-verify with the API test suite after billing lands.
- [ ] SSE token in query param: acceptable for MVP, but ensure access logs on the platform don't get shared, and keep JWT expiry ≤7 days. (Post-launch improvement: short-lived one-time SSE tickets.)
- [ ] Input length caps: `idea_description` ≤ 2,000 chars, chat `message` ≤ 2,000 chars (Pydantic `max_length`) — protects LLM cost.
- [ ] Prompt-injection containment: research/section prompts already treat scraped text as data; verify no scraped content is ever executed or used to build URLs for further fetching beyond the allowlisted providers.
- [ ] Dependency audit: `pip install pip-audit && pip-audit`, `npm audit` — fix criticals.
- [ ] HTTPS everywhere (Vercel/Railway do this automatically); HSTS header via Vercel config.

### 4.2 Reliability

- [ ] Celery retries verified per worker (they exist — test by killing Redis mid-run and restoring).
- [ ] Task time limits: set `task_time_limit=900` (15 min hard) and `task_soft_time_limit=780` in `celery_app.py` so a hung LLM call can't wedge a worker forever.
- [ ] Stuck-session sweeper: a Celery beat task every 10 min that marks sessions stuck >30 min in a non-terminal state as failed and emits `export_failed`-style events so the UI unblocks. (Add `celery beat` as a start command flag: `celery -A app.workers.celery_app worker -B ...` — fine at this scale.)
- [ ] Graceful degradation confirmed: Astra down → Postgres fallback path exercised (unset Astra env vars in a test run); trend feeds down → 90 s timeout path (backend B2.4).

### 4.3 Cost protection

- [ ] Rate limits live (backend B5.1): 5 sessions/hour/user.
- [ ] Global daily circuit breaker: a Redis counter of sessions started per day; if > N (start with 200), return 503 "at capacity" — protects you from a viral spike burning your SerpAPI/Groq budget overnight.
- [ ] Billing alerts set at Groq + SerpAPI + Railway.

### 4.4 Data & privacy

- [ ] Privacy policy + Terms pages live (templates: doc 09 §8).
- [ ] Account deletion path: a `DELETE /users/me` endpoint (cascade sessions/reports, delete R2 objects) — or, for MVP, a documented "email us and we delete within 7 days" process in the privacy policy. Pick one, honor it.
- [ ] Weekly Neon backup routine (doc 07 Part 8) actually scheduled.

### 4.5 Observability

- [ ] Sentry receiving events from API, workers, and frontend.
- [ ] A simple metrics habit: a `/admin/stats` JWT-allowlisted endpoint (your email only) returning counts — signups, sessions today, completion rate (EXPORTED ÷ started), median pipeline duration. Check daily; these four numbers ARE your product dashboard until you outgrow them.

---

## 5. Launch gate

You may announce publicly (doc 09 launch sequence) when **all** are true:

1. Doc 07 Part 7 production smoke test passes 3 days in a row.
2. Billing verification matrix (§3.6) fully green in live mode with your own card.
3. Pipeline completion rate ≥ 90% over ≥ 20 test reports across diverse ideas (fintech, D2C, deep tech, services).
4. Median idea→PDF time ≤ 12 minutes.
5. Privacy/Terms pages linked in the footer.
6. The circuit breaker (§4.3) is deployed — launch-day traffic is exactly when you need it.
