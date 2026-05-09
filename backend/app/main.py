import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db import base as model_registry  # noqa: F401
from app.db.session import dispose_engine
from app.llm.providers import get_llm_provider
from app.llm.providers.anthropic import AnthropicLLMProvider

MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
logger = logging.getLogger(__name__)


def _safe_validation_errors(exc: RequestValidationError):
    errors = exc.errors()
    for error in errors:
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            error["ctx"] = {key: str(value) for key, value in ctx.items()}
    return errors


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.llm_provider == "anthropic" and settings.anthropic_validate_model_on_startup:
        provider = get_llm_provider(settings)
        if isinstance(provider, AnthropicLLMProvider):
            await provider.validate_model()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    def _set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'",
        )
        if settings.environment == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        return _set_security_headers(
            JSONResponse(
                status_code=422,
                content={
                    "detail": {
                        "message": "Request validation failed.",
                        "code": "VALIDATION_ERROR",
                        "errors": _safe_validation_errors(exc),
                    }
                },
            )
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
        return _set_security_headers(
            JSONResponse(
                status_code=500,
                content={
                    "detail": {
                        "message": "Something went wrong.",
                        "code": "INTERNAL_SERVER_ERROR",
                    }
                },
            )
        )

    @app.middleware("http")
    async def harden_request(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in MUTATION_METHODS and origin not in settings.allowed_origins:
            return _set_security_headers(
                JSONResponse(
                    status_code=403,
                    content={"detail": "Origin is not allowed."},
                )
            )
        response = await call_next(request)
        return _set_security_headers(response)

    app.include_router(api_router)
    return app


app = create_app()
