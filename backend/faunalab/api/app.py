"""ASGI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from faunalab.api.errors import AppError, internal_error_response, problem_response
from faunalab.api.images import router as images_router
from faunalab.api.inferences import router as inferences_router
from faunalab.api.jobs import router as jobs_router
from faunalab.api.labels import router as labels_router
from faunalab.api.models import router as models_router
from faunalab.api.sample import router as sample_router
from faunalab.api.spa import SpaStaticFiles
from faunalab.api.splits import router as splits_router
from faunalab.api.state import router as state_router
from faunalab.api.stats import router as stats_router
from faunalab.api.suggestions import router as suggestions_router
from faunalab.jobs.supervisor import start_worker, stop_worker
from faunalab.ml.baseline import register_baseline_model
from faunalab.ml.runtime import try_load_baseline_runtime
from faunalab.ml.session_cache import OnnxSessionCache
from faunalab.persist.store import Store
from faunalab.settings import Settings, get_settings

LOGGER = logging.getLogger("faunalab")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Static UI is mounted last when `web/dist` exists."""

    resolved = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        store = Store(resolved.data_dir)
        store.initialize()
        inspection = register_baseline_model(store, resolved.assets_dir)
        runtime = None
        if inspection.ok:
            runtime = try_load_baseline_runtime(
                inspection.model_path, inspection.class_map
            )
        _app.state.baseline = inspection
        _app.state.baseline_runtime = runtime
        _app.state.onnx_sessions = OnnxSessionCache()
        _app.state.store = store
        worker = start_worker(resolved.data_dir, resolved.assets_dir)
        _app.state.worker = worker
        try:
            yield
        finally:
            stop_worker(worker)
            store.close()

    # Swagger UI / ReDoc は既定で CDN を読む。
    # 実行段階の外部ネット禁止に合わせ HTML は出さず、契約は /openapi.json だけ残す。
    app = FastAPI(
        title="FaunaLab",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    origins = resolved.cors_origin_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return problem_response(
            status=400,
            title="Bad Request",
            code="validation_error",
            detail="要求の内容が不正です。",
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        if isinstance(exc, (StarletteHTTPException, RequestValidationError, AppError)):
            raise exc
        LOGGER.exception("unhandled exception")
        return internal_error_response()

    app.include_router(state_router)
    app.include_router(images_router)
    app.include_router(labels_router)
    app.include_router(splits_router)
    app.include_router(stats_router)
    app.include_router(sample_router)
    app.include_router(models_router)
    app.include_router(inferences_router)
    app.include_router(jobs_router)
    app.include_router(suggestions_router)
    dist = resolved.web_dist_dir
    if dist.is_dir():
        app.mount("/", SpaStaticFiles(directory=dist, html=True), name="ui")
    return app


app = create_app()
