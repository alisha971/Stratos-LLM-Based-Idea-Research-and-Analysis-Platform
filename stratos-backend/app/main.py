from fastapi import FastAPI
from app.api import auth, sse

app = FastAPI(
    title="Stratos Backend",
    version="1.0.0"
)

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(sse.router, prefix="/stream", tags=["SSE"])

@app.get("/")
def health():
    return {"status": "ok", "service": "stratos-backend"}
