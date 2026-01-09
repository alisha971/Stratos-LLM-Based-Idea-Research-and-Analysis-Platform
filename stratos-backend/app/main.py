from fastapi import FastAPI
from contextlib import asynccontextmanager
from threading import Thread

from app.api import auth, sse, orchestrator
from app.utils.redis_sub import start_event_listener

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Thread(
        target=start_event_listener,
        daemon=True,
    ).start()

    yield

    # Shutdown (nothing to clean yet)

app = FastAPI(
    title="Stratos Backend",
    version="1.0.0", 
    lifespan=lifespan,
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(sse.router, prefix="/stream", tags=["SSE"])
app.include_router(orchestrator.router, prefix="/orchestrate", tags=["Orchestrator"])

@app.get("/")
def health():
    return {"status": "ok", "service": "stratos-backend"}
