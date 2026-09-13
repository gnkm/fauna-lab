"""RFC 9457 Problem Details helpers (DESIGN.md 4.2)."""

from __future__ import annotations

from fastapi.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"

ERROR_TITLES: dict[int, str] = {
    400: "Bad Request",
    404: "Not Found",
    409: "Conflict",
    413: "Content Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Content",
    500: "Internal Server Error",
}

ERROR_STATUS: dict[str, int] = {
    "validation_error": 400,
    "image_not_found": 404,
    "model_not_found": 404,
    "job_not_found": 404,
    "image_duplicate": 409,
    "model_not_deletable": 409,
    "payload_too_large": 413,
    "unsupported_media_type": 415,
    "sample_unavailable": 422,
    "empty_test_split": 422,
    "no_active_model": 422,
    "baseline_unavailable": 422,
    "internal_error": 500,
}


class AppError(Exception):
    """Program-interface error that maps to a Problem Details response."""

    def __init__(self, *, status: int, code: str, title: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail

    def to_response(self) -> JSONResponse:
        return problem_response(
            status=self.status,
            title=self.title,
            code=self.code,
            detail=self.detail,
        )


def error_for_code(code: str, detail: str) -> AppError:
    status = ERROR_STATUS[code]
    return AppError(
        status=status,
        code=code,
        title=ERROR_TITLES[status],
        detail=detail,
    )


def image_not_found() -> AppError:
    return error_for_code("image_not_found", "指定した画像は存在しません。")


def model_not_found() -> AppError:
    return error_for_code("model_not_found", "指定したモデル版は存在しません。")


def no_active_model() -> AppError:
    return error_for_code(
        "no_active_model",
        "有効モデルが無いため推論を実行できません。",
    )


def baseline_unavailable() -> AppError:
    return error_for_code(
        "baseline_unavailable",
        "有効モデルの推論成果物が利用できません。",
    )


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
