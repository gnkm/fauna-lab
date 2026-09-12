"""ASGI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from faunalab.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Static UI is mounted last when `web/dist` exists."""

    resolved = settings if settings is not None else get_settings()
    # Swagger UI / ReDoc は既定で CDN を読む。
    # 実行段階の外部ネット禁止に合わせ HTML は出さず、契約は /openapi.json だけ残す。
    app = FastAPI(title="FaunaLab", version="0.1.0", docs_url=None, redoc_url=None)
    origins = resolved.cors_origin_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    dist = resolved.web_dist_dir
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


app = create_app()
