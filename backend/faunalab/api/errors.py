"""RFC 9457 Problem Details helpers (DESIGN.md 4.2)."""

from __future__ import annotations

from fastapi.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"


def problem_response(
    *,
    status: int,
    title: str,
    code: str,
    detail: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_JSON,
        content={
            "type": f"urn:faunalab:error:{code}",
            "title": title,
            "status": status,
            "detail": detail,
            "code": code,
        },
    )


def internal_error_response() -> JSONResponse:
    return problem_response(
        status=500,
        title="Internal Server Error",
        code="internal_error",
        detail="処理中に予期しない誤りが起きました。",
    )
