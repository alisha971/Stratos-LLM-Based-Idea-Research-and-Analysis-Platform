---
name: stratos-security-gate
description: Apply Stratos security rules when touching auth, fetching/scraping code, LLM prompt boundaries, secrets, rate limits, or webhooks — and run the pre-launch security checklist. Use when editing auth/JWT code, safe_fetch, scraper calls, billing webhooks, or when asked to security-review Stratos changes.
---

# Stratos Security Gate

Compressed enforcement of `stratos-launch-plan/11-SECURITY-PLAN.md`. Full details and per-item tests live there; this is what must never regress.

## The golden rule

**Never weaken a security check to make a test or feature pass.** If a security test fails, the code is wrong, not the test. No exceptions, no "temporary" bypasses.

## Non-negotiables by area

**Auth (§1):** JWT decode always pins `algorithms=["HS256"]`; ownership checks on every session/report/export query; cross-user access returns **404, never 403**; production boot must refuse the default `JWT_SECRET` and refuse `DEV_AUTH_BYPASS=true`.

**SSRF (§5) — the scraper is the most dangerous capability:** all outbound page fetches go through `app/utils/safe_fetch.py`: http/https only, ports 80/443, DNS-resolve-then-reject private/loopback/link-local/reserved IPs, re-check on redirects (max 3), 2 MB / 8 s caps. A bare `requests.get(url)` on an internet-derived URL is a blocking review finding. Test URLs that must be blocked: `169.254.169.254`, `localhost:*`, `file://`, `10.x/172.16-31.x/192.168.x`, redirect-to-internal.

**Prompt injection (§6):** internet-derived text goes in `<data>` tags declared as data-not-instructions; never execute/fetch/format LLM- or evidence-derived strings into shell/SQL/paths/URLs; frontend renders markdown WITHOUT raw-HTML passthrough; ReportLab text is XML-escaped; citation URLs sanitized to http(s) before becoming links.

**Secrets (§2):** `.env` gitignored (verify with `git check-ignore`); no secrets in code, logs, events, or error messages; before commit run `rg -i '(sk_live|sk_test|whsec_|AKIA|ghp_)[A-Za-z0-9]' --glob '!*.md'` — must be empty.

**Cost abuse (§4):** expensive endpoints keep rate limits (start-session 5/hr/user) + plan quota 402s + the global daily circuit breaker. Never remove a budget cap to "fix" a timeout.

**Webhooks (§7):** verify provider signature BEFORE parsing body; handlers idempotent (replay-safe).

**Inputs (§3):** user text capped (idea/message ≤ 2000 chars), control chars stripped, IDs validated as UUIDs at the route layer; ORM only — no raw SQL.

## Pre-launch gate

Before any public deploy, run the full checklist at the end of `11-SECURITY-PLAN.md` and paste evidence per line (test outputs, curl headers, boot-refusal errors). All boxes or no launch.
