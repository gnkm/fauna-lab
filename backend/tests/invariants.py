"""Observation-state invariants (REQ-DATA-003〜010) for acceptance tests."""

from __future__ import annotations

from typing import Any

ALLOWED_SPLITS = frozenset({"train", "val", "test", "unassigned"})
ALLOWED_SOURCES = frozenset({"human", "model_suggested"})
JOB_STATUSES = frozenset({"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"})


def without_observed_at(body: dict[str, Any]) -> dict[str, Any]:
    rest = dict(body)
    rest.pop("observed_at", None)
    return rest


def assert_observation_invariants(state: dict[str, Any]) -> None:
    """VER-DATA-002: `_state` から 3.5.3 の不変条件を検算する。"""

    images = state["images"]
    refs = [item["ref"] for item in images]
    assert len(refs) == len(set(refs))
    digests = [item["sha256"] for item in images]
    assert len(digests) == len(set(digests))
    for image in images:
        assert image["split"] in ALLOWED_SPLITS
        label = image["label"]
        suggestion = image["suggestion"]
        if label is not None:
            assert suggestion is None
            assert label["source"] in ALLOWED_SOURCES
            assert isinstance(label["class_id"], str)
        if suggestion is not None:
            assert label is None
            assert 0.0 <= float(suggestion["confidence"]) <= 1.0

    models = state["models"]
    model_refs = [item["ref"] for item in models]
    assert len(model_refs) == len(set(model_refs))
    versions = [item["version"] for item in models]
    assert len(versions) == len(set(versions))
    actives = [item for item in models if item["active"]]
    assert len(actives) <= 1
    for model in models:
        if model["version"] == 0:
            assert model["builtin"] is True
        else:
            assert model["builtin"] is False

    jobs = state["jobs"]
    job_refs = [item["ref"] for item in jobs]
    assert len(job_refs) == len(set(job_refs))
    running = [item for item in jobs if item["status"] == "RUNNING"]
    assert len(running) <= 1
    for job in jobs:
        assert job["status"] in JOB_STATUSES
        if job["status"] == "FAILED":
            assert job["failed"] is True
        else:
            assert job["failed"] is False
        # REQ-DATA-010: 削除済モデルを指す model_ref は models に無くてよい。
        if job["model_ref"] is not None:
            assert isinstance(job["model_ref"], str)

    inferences = state["inferences"]
    inf_refs = [item["ref"] for item in inferences]
    assert len(inf_refs) == len(set(inf_refs))
    image_ref_set = set(refs)
    for item in inferences:
        assert item["image_ref"] in image_ref_set


def assert_job_kept_after_model_delete(
    state: dict[str, Any], *, job_ref: str, deleted_model_ref: str
) -> None:
    """REQ-DATA-010: モデル版削除後もジョブ履歴が `_state` に残る。"""

    jobs = {item["ref"]: item for item in state["jobs"]}
    assert job_ref in jobs
    assert jobs[job_ref]["status"] in JOB_STATUSES
    assert jobs[job_ref]["model_ref"] in {deleted_model_ref, None}
    visible = {item["ref"] for item in state["models"]}
    assert deleted_model_ref not in visible
