"""FastAPI application factory.

    uvicorn nazeer_api.main:app            # settings from the environment / .env

The browser reaches this API through the web app's /api/* rewrite (same origin), so cookies are
first-party. CORS stays strict (credentials only for ALLOWED_ORIGINS) as a second layer.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from nazeer.config import enforce_offline
from nazeer.safe_log import configure_logging
from nazeer_api import __version__
from nazeer_api.config import Settings, get_settings
from nazeer_api.db import make_engine, make_sessionmaker
from nazeer_api.routers import auth, datasets, invitations, orgs, shares
from nazeer_api.security import API_HEADERS, HSTS, CSRF_HEADER, RateLimiter

log = logging.getLogger("nazeer_api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    enforce_offline()
    app = FastAPI(title="Nazeer API", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    engine = make_engine(settings.database_url, settings.database_ca_pem)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.limiter = RateLimiter()

    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_origin_regex=settings.allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", CSRF_HEADER],
        max_age=600)

    @app.middleware("http")
    async def secure_headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in API_HEADERS.items():
            response.headers.setdefault(k, v)
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": _code_for(exc.status_code)}
        return JSONResponse(detail, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Field names and error types only: pydantic messages can quote the submitted value.
        fields = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) for e in exc.errors()})
        return JSONResponse({"code": "invalid_request", "fields": fields}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=True)
        return JSONResponse({"code": "internal_error"}, status_code=500)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    app.include_router(auth.router)
    app.include_router(invitations.router)
    app.include_router(orgs.router)
    app.include_router(datasets.router)
    app.include_router(shares.org_router)
    app.include_router(shares.router)
    return app


def _code_for(status: int) -> str:
    return {401: "not_authenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
        status, "error")


def __getattr__(name: str):
    # `uvicorn nazeer_api.main:app` builds the app lazily, so importing this module (tests) needs no env.
    if name == "app":
        return create_app()
    raise AttributeError(name)
