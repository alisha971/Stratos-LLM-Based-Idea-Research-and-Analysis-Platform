# 05 — Oracle Cloud Deploy (fast-ship hosting decision)

> **Decision (2026-08-21, superseding 2026-08-20): we are launching on Oracle
> Cloud Always Free, not GCP.** The GCP plan relied on the $300/90-day trial
> credit, which isn't available to us (no card/credits). Oracle's **Always
> Free** tier gives an ARM VM (up to 4 OCPU / 24 GB RAM / 200 GB disk) that
> never expires and never bills — no trial clock to watch, no exit plan
> needed. Frontend stays on **Vercel** (free Hobby); Postgres stays on
> **Neon** (free); evidence store stays on **Astra DB** (free). Cash cost at
> launch: **$0**, indefinitely (plus an optional ~$10–15/yr domain).
>
> This doc replaces Part 4 of `../stratos-launch-plan/07-DEPLOYMENT-GUIDE.md`
> (the Railway part) and supersedes the earlier GCP version of this file.
> Everything else in that guide — GitHub, Neon/Astra setup, Vercel (Part 5),
> domain wiring, OAuth origins, the Part-7 smoke test — still applies
> verbatim.

## Why Oracle Cloud (decision record)

- Vercel cannot host the backend (Celery worker + Redis pub/sub SSE +
  local-disk PDFs need an always-on process and a persistent filesystem).
- Railway works but is ~$10–20/month from day one (trial credits only).
- GCP's free trial requires a card and burns down a 90-day credit — not
  usable here since we don't have that credit available.
- Oracle's **Always Free** tier is a genuinely permanent free allocation, not
  a trial: up to 4 Ampere A1 (ARM) OCPUs and 24 GB RAM total, split across up
  to 4 VM instances, plus 200 GB block storage, 10 TB/month egress, and a
  free load balancer — all forever, no time limit, no card charge. This is
  strictly more headroom than the GCP e2-small it replaces, so the
  embedding-worker (PyTorch/sentence-transformers) OOM risk that ruled out
  GCP's Always-Free e2-micro goes away too.
- Known friction (be aware, not blocking): Oracle's signup does stricter
  identity/card verification than GCP or AWS, and in some regions the free
  ARM shape can show "Out of capacity" when first requesting an instance —
  usually resolved by trying a different Availability Domain or retrying over
  a day or two. Budget an extra 30–60 minutes for signup versus GCP.
- Lock-in guard unchanged: Postgres stays on **Neon**, not any Oracle DB
  service. Migrating off Oracle later = move one docker-compose file and
  re-point one DNS record.

## Topology

One VM runs everything backend, via docker-compose (identical shape to the
GCP plan — only the cloud provider changes):

```
┌──────────── Oracle Always-Free ARM VM ──────────┐
│  caddy (TLS, :443 → :8000)                       │
│  stratos-backend container                       │
│    ├─ uvicorn app.main:app  (API + SSE)          │
│    └─ celery worker --concurrency=2               │
│  redis container (db 0 broker, db 1 pubsub)      │
│  /srv/stratos/exports  (PDFs on VM disk)          │
└───────────────────────────────────────────────────┘
        ▲ https://api.yourdomain.com
Vercel (frontend) ── Neon (Postgres) ── Astra DB
```

Same single-container trick as task 3.1 (API + worker share a filesystem, so
local-disk PDF export works); the "Railway volume" is just the VM's disk.

## Step-by-step

### 1. Create the account + VM

1. `cloud.oracle.com` → **Sign up for Free Tier** → complete identity
   verification (card required for verification only, never charged unless
   you explicitly upgrade to Pay As You Go).
2. Once in the console: **Compute → Instances → Create Instance**:
   - Name `stratos-backend`.
   - **Image and shape → Change shape** → select **Ampere** (ARM) →
     `VM.Standard.A1.Flex` → set **2 OCPU / 12 GB RAM** to start (well inside
     the 4 OCPU / 24 GB free allowance; bump to 4/24 later if needed — free
     either way).
   - Image: **Ubuntu 22.04** (or latest LTS) — Ampere/ARM build (default when
     the Ampere shape is selected).
   - Boot volume: default is fine (up to 200 GB total block storage is free
     across all your volumes).
   - **Add SSH keys**: let it generate a key pair, download the private key
     — you'll need it to log in.
   - Networking: use the default VCN it offers to create; **do not** attach
     a paid-tier resource anywhere in the wizard (everything defaults to
     free-eligible, but double-check the shape/volume summary before
     clicking Create — it warns if something isn't Always-Free eligible).
3. If you hit **"Out of host capacity"** creating the Ampere shape: try a
   different Availability Domain (dropdown in the shape config), or retry
   after a few hours — this is a known Always-Free ARM quirk, not an account
   problem.
4. Once running, note the VM's **public IP address**.
5. **Networking → Virtual Cloud Networks → your VCN → Security Lists** →
   default security list → **Add Ingress Rules**: allow TCP 80 and 443 from
   `0.0.0.0/0` (Oracle's default security list only opens 22 by default,
   unlike GCP/AWS — this step is easy to miss and is the #1 cause of "caddy
   works locally but the domain times out").

### 2. Install Docker and get the code

SSH in with the downloaded key (`ssh -i ~/.ssh/oracle_key ubuntu@<public-ip>`),
then:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # log out/in after this
git clone https://github.com/<you>/stratos.git ~/stratos
```

Ubuntu's own firewall (`iptables`/`ufw`) also ships pre-configured on Oracle
images and can double-block ports even after the console security list is
open. If `curl localhost/healthz` works on the VM but the public domain
doesn't, check `sudo iptables -L` / `sudo ufw status` and allow 80/443 there
too (or `sudo ufw disable` if you're relying solely on the VCN security list).

### 3. Production compose + TLS

Create `~/stratos/deploy/docker-compose.prod.yml` on the VM (backend image from
task 3.1's Dockerfile + `start.sh`, plus redis and caddy):

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes: ["redis-data:/data"]
  backend:
    build: ../stratos-backend
    restart: unless-stopped
    env_file: ../stratos-backend/.env   # created in step 4
    volumes: ["/srv/stratos/exports:/app/exports"]
    depends_on: [redis]
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy-data:/data
volumes: { redis-data: {}, caddy-data: {} }
```

`deploy/Caddyfile` (Caddy auto-issues the TLS cert):

```
api.yourdomain.com {
    reverse_proxy backend:8000
}
```

DNS: add an **A record** `api.yourdomain.com` → the VM's public IP (Oracle's
free-tier public IP is already static/persistent by default — no separate
"promote to static" step like GCP). No domain yet? Use a free **Cloudflare
Tunnel** instead of caddy, or grab the domain now — Google OAuth origins want
a stable HTTPS URL anyway.

### 4. Backend env

`~/stratos/stratos-backend/.env` on the VM — all values per doc 03, with the
Oracle-specific ones being:

```
ENV=production
REDIS_BROKER_URL=redis://redis:6379/0
REDIS_PUBSUB_URL=redis://redis:6379/1
EXPORT_STORAGE=local
FRONTEND_ORIGIN=https://yourdomain.com
DATABASE_URL=<Neon pooled connection string>
```

(`redis` is the compose service name — the containers share a network.)

### 5. Boot + bootstrap

```bash
cd ~/stratos/deploy
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python scripts/create_tables.py
curl -s https://api.yourdomain.com/healthz   # → {"ok": true}
docker compose -f docker-compose.prod.yml logs backend | grep -i celery  # worker banner
```

### 6. Frontend + wiring (unchanged from doc 07)

- Vercel: root dir `stratos-frontend`,
  `NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com`,
  `NEXT_PUBLIC_GOOGLE_CLIENT_ID=<client id>` (doc 07 Part 5).
- Domain + Google OAuth origins + CORS exact-match (doc 07 Part 6).
- Run the doc 07 Part 7 smoke test, minus billing rows.

### 7. Deploying updates

```bash
cd ~/stratos && git pull
cd deploy && docker compose -f docker-compose.prod.yml up -d --build
```

(Manual is fine for the beta; CI-driven deploys are a premium-plan concern.)

## Ops notes

- **Restarts:** `restart: unless-stopped` + Docker's systemd service cover VM
  reboots — verify once with a reboot from the console.
- **PDFs** live on the VM disk at `/srv/stratos/exports` (survives container
  rebuilds). VM dies = PDFs gone; acceptable for beta (same stance as the
  Railway-volume plan). Oracle doesn't offer free automated snapshots the way
  GCP does — if you want a safety net, a weekly `tar` of `/srv/stratos/exports`
  copied off-box (e.g. to a free-tier Backblaze B2 or R2 bucket) costs
  pennies and a cron line.
- **Logs:** `docker compose logs -f backend` is your Railway-logs equivalent.
- **Memory:** watch `docker stats` during the first few reports. At 12 GB RAM
  you have far more headroom than the GCP e2-small ever had; resize the
  instance shape up to 24 GB in the console (free, no redeploy of code needed)
  if you still see pressure.
- **ARM gotcha:** the VM is `aarch64`, not `x86_64`. If any Docker base image
  or Python wheel in `stratos-backend/Dockerfile`/`requirements.txt` doesn't
  ship an ARM build, the `docker compose build` step will fail or fall back to
  slow QEMU emulation. Check this once locally before relying on it:
  `docker buildx build --platform linux/arm64 -t stratos-backend-arm-test .`
  from `stratos-backend/`. PyTorch/sentence-transformers (embedding worker)
  and Playwright/Chromium (if used for scraping) are the two most likely to
  need an ARM-specific base image or install path — verify both explicitly.

## Long-term

Because this is an Always-Free allocation (not a trial), there is no exit
deadline to plan around — unlike the GCP doc's "trial exit plan by day ~80."
Revisit hosting only if the beta outgrows one VM's worth of traffic, at which
point the same options apply as before: pay for a bigger Oracle shape (still
cheap), move to Railway/GCP for less ops overhead, or split services out.
Because Postgres/Astra/Vercel were never on Oracle, any future move is still
a one-VM swap.
