"""OpenAPI 3.1 骨格の契約（F006 / REQ-API-002〜007）。

実装が無くても文書として閉じていることを確認する。VER-API-001 の
「文書に 7 類が異なるステータスとして載っている」部分に対応する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "openapi.yaml"

# REQ-API-003 の 7 状況。DESIGN.md 4.1 および openapi.yaml の components.responses。
SRS_SITUATIONS: dict[str, str] = {
    "要求内容の誤り": "400",
    "対象の不在": "404",
    "現在の状態では実行できない操作": "409",
    "前提条件の不成立": "422",
    "許可されない媒体型": "415",
    "上限を超える大きさ": "413",
    "システム内部の予期しない誤り": "500",
}

ERROR_CODES = (
    "validation_error",
    "unsupported_media_type",
    "payload_too_large",
    "image_not_found",
    "job_not_found",
    "model_not_found",
    "inference_not_found",
    "suggestion_not_found",
    "image_duplicate",
    "job_not_cancelable",
    "model_not_deletable",
    "training_precondition",
    "no_active_model",
    "empty_test_split",
    "baseline_unavailable",
    "sample_unavailable",
    "internal_error",
)

PATHS = (
    "/api/_state",
    "/api/images",
    "/api/images/{ref}",
    "/api/images/{ref}/thumbnail",
    "/api/images/{ref}/label",
    "/api/labels/bulk",
    "/api/splits",
    "/api/stats",
    "/api/jobs",
    "/api/jobs/{ref}",
    "/api/jobs/{ref}/logs",
    "/api/jobs/{ref}/cancel",
    "/api/models",
    "/api/models/{ref}",
    "/api/models/{ref}/activate",
    "/api/models/{ref}/evaluate",
    "/api/inferences",
    "/api/suggestions",
    "/api/suggestions/accept",
    "/api/suggestions/accept-by-threshold",
    "/api/suggestions/reject",
    "/api/sample/import",
)


def test_openapi_document_exists_as_31() -> None:
    """Issue #7 の検証欄と同じ条件。"""
    assert OPENAPI_PATH.exists(), "openapi.yaml or openapi.json"
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    assert "/api/_state" in text
    assert "openapi" in text.lower() and "3.1" in text


def test_error_schema_is_problem_details() -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    assert "application/problem+json" in text
    assert "urn:faunalab:error:" in text
    for field in ("type", "title", "status", "detail", "code"):
        assert field in text
    lowered = text.lower()
    assert "stacktrace" not in lowered
    assert "stack_trace" not in lowered
    assert "traceback" not in lowered


def test_req_api_003_situations_have_distinct_statuses() -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    statuses = list(SRS_SITUATIONS.values())
    assert len(set(statuses)) == 7
    for situation, status in SRS_SITUATIONS.items():
        assert situation in text, situation
        marker = f"x-srs-situation: {situation}"
        assert marker in text
        assert f'"{status}"' in text or f"{status}:" in text


def test_error_code_vocabulary_is_enumerated() -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    for code in ERROR_CODES:
        assert f"- {code}" in text, code


def test_pagination_and_cors_are_documented() -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    assert "name: limit" in text
    assert "name: offset" in text
    assert "total:" in text
    assert "maximum: 200" in text
    assert "FAUNALAB_CORS_ORIGINS" in text


def test_program_interface_paths_are_declared() -> None:
    text = OPENAPI_PATH.read_text(encoding="utf-8")
    for path in PATHS:
        assert path in text, path


def test_openapi_yaml_parses_and_maps_seven_statuses() -> None:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert doc["openapi"] == "3.1.0"
    assert "/api/_state" in doc["paths"]
    responses = doc["components"]["responses"]
    by_situation = {
        body["x-srs-situation"]: str(example["value"]["status"])
        for body in responses.values()
        for example in body["content"]["application/problem+json"]["examples"].values()
    }
    assert by_situation == SRS_SITUATIONS
    assert len(set(by_situation.values())) == 7
    enum_codes = doc["components"]["schemas"]["ErrorCode"]["enum"]
    assert list(ERROR_CODES) == enum_codes
    problem = doc["components"]["schemas"]["Problem"]
    assert problem["additionalProperties"] is False
    assert set(problem["required"]) == {"type", "title", "status", "detail", "code"}
