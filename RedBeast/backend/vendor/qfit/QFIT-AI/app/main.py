"""Q-FIT FastAPI application."""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.dependencies import Container, error_envelope
from app.api.routes import candidates, chat, health, knowledge, objects, observations, spectrum
from app.models.responses import QFitResponse
from app.config import API_PREFIX, APP_FULL_NAME, APP_NAME, APP_VERSION, Settings, get_settings
from app.utils.errors import QFitError
from app.utils.logging import configure_logging, get_logger, request_id_var

log = get_logger("api")


def _json(response_model, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content=response_model.model_dump(mode="json"))


def _validation_message(errors: list[dict]) -> tuple[str, list[dict]]:
    items = [{"field": ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path")),
              "problem": e.get("msg", "invalid")} for e in errors[:10]]
    text = "; ".join(f"{i['field'] or 'request'}: {i['problem']}" for i in items)
    return f"Invalid request: {text}", items


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container or Container(settings)
        log.info("Q-FIT started", extra={"version": APP_VERSION,
                                         "ai_configured": app.state.container.ai_configured})
        yield
        await app.state.container.aclose()

    app = FastAPI(title=f"{APP_NAME} - {APP_FULL_NAME}", version=APP_VERSION, lifespan=lifespan,
                  description="AI-powered astronomical data retrieval backend for NASA SPHEREx data.",
                  docs_url="/docs", openapi_url="/openapi.json")

    origins = settings.cors_origin_list
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type", "X-Request-ID", "X-QFit-Token"], expose_headers=["X-Request-ID"],
                       allow_credentials=False)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = (request.headers.get("X-Request-ID") or uuid.uuid4().hex)[:64]
        token = request_id_var.set(rid)
        started = time.monotonic()
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > settings.max_request_body_bytes:
                response = _json(error_envelope("payload_too_large", "Request body is too large."), 413)
            elif request.method == "POST" and not length:
                body = await request.body()  # chunked upload: measure it
                response = (_json(error_envelope("payload_too_large", "Request body is too large."), 413)
                            if len(body) > settings.max_request_body_bytes else await call_next(request))
            else:
                response = await call_next(request)
        except Exception:
            log.exception("unhandled error")  # full trace stays in the server log only
            response = _json(error_envelope("internal_error", "An unexpected internal error occurred."), 500)
        try:
            response.headers["X-Request-ID"] = rid
            log.info("request", extra={"method": request.method, "path": request.url.path,
                                       "status": response.status_code,
                                       "duration_ms": round((time.monotonic() - started) * 1000)})
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(QFitError)
    async def qfit_error(_: Request, exc: QFitError):
        return _json(error_envelope(exc.code, exc.message, retryable=exc.retryable, details=exc.details),
                     exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def request_invalid(_: Request, exc: RequestValidationError):
        message, items = _validation_message(exc.errors())
        return _json(error_envelope("invalid_input", message, details={"fields": items}), 422)

    @app.exception_handler(ValidationError)
    async def model_invalid(_: Request, exc: ValidationError):
        message, items = _validation_message(exc.errors())
        return _json(error_envelope("invalid_input", message, details={"fields": items}), 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _json(error_envelope(code, str(exc.detail)), exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("unhandled error")  # full trace stays in the server log only
        return _json(error_envelope("internal_error", "An unexpected internal error occurred."), 500)

    for module in (health, chat, objects, observations, spectrum, knowledge, candidates):
        app.include_router(module.router, prefix=API_PREFIX)
    # Root aliases: the web front end calls /health and /chat without the prefix.
    app.add_api_route("/health", health.health, methods=["GET"], response_model=QFitResponse,
                      tags=["system"], summary="Backend health (alias of /api/v1/health)")
    app.add_api_route("/chat", chat.chat, methods=["POST"], response_model=QFitResponse,
                      tags=["assistant"], summary="Natural-language assistant (alias of /api/v1/chat)")

    @app.get("/", include_in_schema=False)
    async def root():
        return {"assistant": APP_NAME, "version": APP_VERSION, "docs": "/docs",
                "health": f"{API_PREFIX}/health", "capabilities": f"{API_PREFIX}/capabilities"}

    return app


app = create_app()
