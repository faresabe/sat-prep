from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.logging import configure_logging, log


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("app_starting", env=settings.environment)
    yield
    log.info("app_shutting_down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAT Prep API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.environment}

    return app


app = create_app()