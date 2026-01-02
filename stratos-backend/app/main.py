from fastapi import FastAPI
from app.api import auth, sse
from app.api import auth, sse, orchestrator

app = FastAPI(
    title="Stratos Backend",
    version="1.0.0"
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(sse.router, prefix="/stream", tags=["SSE"])
app.include_router(orchestrator.router, prefix="/orchestrate", tags=["Orchestrator"])

@app.get("/")
def health():
    return {"status": "ok", "service": "stratos-backend"}
