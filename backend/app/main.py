"""Main FastAPI app: middleware, exception handlers, router wiring.

The app serves both:
  - /api/*        — JSON API (auth, accounts, transactions, statements, notifications)
  - /*            — Jinja2-rendered HTML pages (auth screens, dashboard, etc.)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import Base, engine
from app.exceptions import OrionError
from app.logging_config import configure_logging, get_logger
from app.middleware import RequestIdMiddleware
from app.routes import (
    accounts, admin, auth, notifications, pages, statements,
    totp, transactions, webhooks,
)


# ────────────────────────── Lifespan ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("app.startup")
    log.info("app.starting", env=settings.env, db=settings.database_url.split("://")[0])
    # Create tables on first run if using SQLite (dev convenience).
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    yield
    log.info("app.shutdown")


# ────────────────────────── App + middleware ──────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Orion Banking API — FastAPI + Jinja2 monolith",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Gzip responses > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — must come before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID + audit trail
app.add_middleware(RequestIdMiddleware)


# ────────────────────────── Exception handlers ─────────────────────
@app.exception_handler(OrionError)
async def orion_error_handler(request: Request, exc: OrionError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# ────────────────────────── Static + templates ─────────────────────
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Expose templates to page routes via app state (cleaner than importing everywhere)
app.state.templates = templates


# ────────────────────────── Health ─────────────────────────────────
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "app": settings.app_name, "env": settings.env}


@app.get("/healthz", tags=["health"])
def healthz(db_check: bool = False):
    """Liveness/readiness probe."""
    if db_check:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    return {"status": "ok"}


# ────────────────────────── Routers ────────────────────────────────
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(statements.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(totp.router)
app.include_router(pages.router)  # Jinja2 HTML routes — last so /api takes precedence


# ────────────────────────── Root redirect ──────────────────────────
@app.get("/", include_in_schema=False)
def root_redirect():
    """Send users to /login by default; /dashboard if logged in (front-end decides)."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/login", status_code=302)
