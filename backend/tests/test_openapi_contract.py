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

    situation_schemas = {
        "要求内容の誤り": ("ProblemBadRequest", 400, {"validation_error"}),
        "対象の不在": (
            "ProblemNotFound",
            404,
            {
                "image_not_found",
                "job_not_found",
                "model_not_found",
                "inference_not_found",
                "suggestion_not_found",
            },
        ),
        "現在の状態では実行できない操作": (
            "ProblemConflict",
            409,
            {"image_duplicate", "job_not_cancelable", "model_not_deletable"},
        ),
        "前提条件の不成立": (
            "ProblemUnprocessable",
            422,
            {
                "training_precondition",
                "no_active_model",
                "empty_test_split",
                "baseline_unavailable",
                "sample_unavailable",
            },
        ),
        "許可されない媒体型": (
            "ProblemUnsupportedMediaType",
            415,
            {"unsupported_media_type"},
        ),
        "上限を超える大きさ": ("ProblemPayloadTooLarge", 413, {"payload_too_large"}),
        "システム内部の予期しない誤り": (
            "ProblemInternalError",
            500,
            {"internal_error"},
        ),
    }
    for situation, (schema_name, status, codes) in situation_schemas.items():
        response_name = {
            "ProblemBadRequest": "BadRequest",
            "ProblemNotFound": "NotFound",
            "ProblemConflict": "Conflict",
            "ProblemUnprocessable": "Unprocessable",
            "ProblemUnsupportedMediaType": "UnsupportedMediaType",
            "ProblemPayloadTooLarge": "PayloadTooLarge",
            "ProblemInternalError": "InternalError",
        }[schema_name]
        assert responses[response_name]["x-srs-situation"] == situation
        schema_ref = responses[response_name]["content"]["application/problem+json"][
            "schema"
        ]["$ref"]
        assert schema_ref.endswith(schema_name)
        constraint = doc["components"]["schemas"][schema_name]["allOf"][1]["properties"]
        assert constraint["status"]["const"] == status
        allowed = (
            {constraint["code"].get("const")}
            if "const" in constraint["code"]
            else set(constraint["code"]["enum"])
        )
        assert allowed == codes


def test_metrics_require_fixed_eight_classes() -> None:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    per_class = doc["components"]["schemas"]["PerClassMetrics"]
    class_ids = [
        "samoyed",
        "great_pyrenees",
        "boxer",
        "american_bulldog",
        "chihuahua",
        "miniature_pinscher",
        "pomeranian",
        "havanese",
    ]
    assert per_class["additionalProperties"] is False
    assert per_class["required"] == class_ids
    assert list(per_class["properties"]) == class_ids
    matrix = doc["components"]["schemas"]["ConfusionMatrix"]
    assert matrix["properties"]["matrix"]["minItems"] == 8
    assert matrix["properties"]["matrix"]["maxItems"] == 8
    row = doc["components"]["schemas"]["ConfusionMatrixRow"]
    assert row["minItems"] == 8
    assert row["maxItems"] == 8
    labels = matrix["properties"]["labels"]["prefixItems"]
    assert [item["const"] for item in labels] == class_ids


def test_inference_request_caps_total_at_20() -> None:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    request = doc["components"]["schemas"]["InferenceCreateRequest"]
    assert len(request["oneOf"]) == 3
    files_only = doc["components"]["schemas"]["InferenceCreateFilesOnly"]
    refs_only = doc["components"]["schemas"]["InferenceCreateRefsOnly"]
    assert files_only["properties"]["files"]["maxItems"] == 20
    assert "refs" not in files_only["properties"]
    assert refs_only["properties"]["refs"]["maxItems"] == 20
    assert "files" not in refs_only["properties"]
    mixed = doc["components"]["schemas"]["InferenceCreateMixed"]["oneOf"]
    assert mixed
    for branch in mixed:
        n_files = branch["properties"]["files"]["maxItems"]
        n_refs = branch["properties"]["refs"]["maxItems"]
        assert n_files == branch["properties"]["files"]["minItems"]
        assert n_files + n_refs == 20


def test_state_uses_observation_image_schema() -> None:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    required = doc["components"]["schemas"]["ObservationImage"]["required"]
    assert required == ["ref", "sha256", "split", "label", "suggestion"]
    assert "original_name" not in required
    state_items = doc["components"]["schemas"]["ObservationState"]["properties"][
        "images"
    ]["items"]["$ref"]
    assert state_items.endswith("ObservationImage")
    extra = doc["components"]["schemas"]["Image"]["allOf"][1]["required"]
    assert "original_name" in extra
    page_items = doc["components"]["schemas"]["ImagePage"]["allOf"][1]["properties"][
        "items"
    ]["items"]["$ref"]
    assert page_items.endswith("Image")


def test_state_uses_observation_model_schema() -> None:
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    required = doc["components"]["schemas"]["ObservationModel"]["required"]
    assert required == ["ref", "version", "builtin", "active", "metrics"]
    assert "created_at" not in required
    extra = doc["components"]["schemas"]["Model"]["allOf"][1]["required"]
    assert "created_at" in extra
    state_items = doc["components"]["schemas"]["ObservationState"]["properties"][
        "models"
    ]["items"]["$ref"]
    assert state_items.endswith("ObservationModel")
    page_items = doc["components"]["schemas"]["ModelPage"]["allOf"][1]["properties"][
        "items"
    ]["items"]["$ref"]
    assert page_items.endswith("Model")
