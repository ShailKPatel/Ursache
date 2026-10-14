from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from ursache.api.health import health_service
from ursache.api.routes import health
from ursache.config import Settings, get_settings
from ursache.llm.quota import QuotaExceeded
from ursache.logging import configure_logging
from ursache.telemetry import configure_tracing


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.environment == "prod")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with health_service(settings) as service:
            app.state.health_service = service
            app.state.quota = service.quota
            try:
                yield
            finally:
                if tracer_provider is not None:
                    tracer_provider.shutdown()

    app = FastAPI(title="Ursache API", version="0.1.0", lifespan=lifespan)

    limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse({"detail": f"rate limit exceeded: {exc.detail}"}, status_code=429)

    @app.exception_handler(QuotaExceeded)
    async def _quota_exceeded(_request: Request, exc: QuotaExceeded) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "provider": exc.provider, "model": exc.model}, status_code=429
        )

    app.include_router(health.router)
    tracer_provider = configure_tracing(settings, app)
    return app
