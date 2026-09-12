from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from app.config import settings
from app.api import auth, workspaces, documents, query


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure Qdrant collection exists at startup
    try:
        from app.ingestion import qdrant_mgr
        qdrant_mgr.ensure_collection()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Qdrant not available at startup: %s", exc)
    yield


app = FastAPI(
    title="ContextGuard API",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

if settings.ALLOWED_HOSTS != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(documents.router)
app.include_router(query.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "ContextGuard API"}


@app.get("/ready")
def ready():
    """Confirms critical dependencies are reachable. No model inference here."""
    from app.database import engine
    checks: dict[str, str] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        from redis import Redis
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    try:
        from qdrant_client import QdrantClient
        QdrantClient(
            url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=2,
        ).get_collections()
        checks["qdrant"] = "ok"
    except Exception as exc:
        checks["qdrant"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    from fastapi import Response
    import json
    return Response(
        content=json.dumps({"status": "ready" if healthy else "not ready", "checks": checks}),
        status_code=200 if healthy else 503,
        media_type="application/json",
    )
