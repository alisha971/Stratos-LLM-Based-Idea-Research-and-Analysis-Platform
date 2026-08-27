Everything's already set up locally (stratos-backend/venv, both .env files exist), so this is the day-to-day startup. Four terminals, in this order:

1. Infra (Postgres + Redis) — from stratos-backend/:

```
cd stratos-backend
docker compose up -d
```

(the compose file lives in stratos-backend/docker-compose.yml, not the repo root — postgres:16 on 5432, redis:7 on 6379)

2. API

```
cd stratos-backend
& ".\venv\Scripts\Activate.ps1"
uvicorn app.main:app --reload
```

→ http://127.0.0.1:8000

3. Celery worker (separate terminal, same venv)

```
cd stratos-backend
& ".\venv\Scripts\Activate.ps1"
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

--pool=solo is required on Windows.

4. Frontend

```
cd stratos-frontend
npm run dev
```

→ http://localhost:3000 (backend must be up first)

First-time-only extras, if you ever rebuild the DB: python scripts/create_tables.py (with the venv active), and npm install / cp .env.example .env.local on the frontend.

Checks: python -m pytest tests -q (backend), npm test + npm run lint (frontend).