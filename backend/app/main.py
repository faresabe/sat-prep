from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, log
from app.modules.attempts.router import router as submit_router
from app.modules.attempts.attempt_router import router as attempt_router
from app.modules.analytics.router import router as analytics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("app_starting", env=settings.environment)
    yield
    log.info("app_shutting_down")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # CORS preflights: pass through immediately, no logging needed
        if request.method == "OPTIONS":
            return await call_next(request)

        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=request.headers.get("X-User-Id", "anonymous"),
        )
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        log.info("request", status=response.status_code, latency_ms=elapsed_ms)
        response.headers["X-Request-Id"] = request_id
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAT Prep API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    # Order matters: last add_middleware = outermost wrapper.
    # We want: CORS (outermost) → RequestLogger → routes
    # So register RequestLogger first, then CORS.
    app.add_middleware(RequestLoggerMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handlers ───────────────────────────────────────────
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        log.warning(
            "app_error",
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.public_message},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        log.error("integrity_error", pgcode=getattr(exc.orig, "pgcode", None))
        return JSONResponse(status_code=409, content={"detail": "conflict"})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal error"},
        )

    # ── Routers ─────────────────────────────────────────────────────────────
    app.include_router(submit_router, prefix="/api/v1")
    app.include_router(attempt_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.environment}

    return app


app = create_app()
