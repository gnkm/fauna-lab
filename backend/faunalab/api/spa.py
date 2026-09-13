"""Serve the Vite SPA so History API URLs survive reload (REQ-UI-002)."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


def _is_api_path(path: str) -> bool:
    first = path.lstrip("/").split("/", 1)[0]
    return first == "api"


class SpaStaticFiles(StaticFiles):
    """Return index.html for unknown UI paths. Never mask `/api/` 404s."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and not _is_api_path(path):
                return await super().get_response("index.html", scope)
            raise
        if response.status_code == 404 and not _is_api_path(path):
            return await super().get_response("index.html", scope)
        return response
