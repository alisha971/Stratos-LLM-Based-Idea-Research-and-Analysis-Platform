from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import auth, orchestrator, reports, sse
from app.config import settings
from app.utils.rate_limit import limiter
from app.utils.redis_sub import start_event_listener


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background Redis listener that drives orchestrator state transitions.
    Thread(target=start_event_listener, daemon=True).start()
    yield


app = FastAPI(
    title="Stratos Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — exact-match allowlist (security §7.1)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(sse.router, prefix="/stream", tags=["SSE"])
app.include_router(orchestrator.router, prefix="/orchestrate", tags=["Orchestrator"])
app.include_router(reports.router, tags=["Reports"])


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def health():
    return {"status": "ok", "service": "stratos-backend"}
