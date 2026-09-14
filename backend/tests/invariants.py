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

    inferences = state["inferences"]
    inf_refs = [item["ref"] for item in inferences]
    assert len(inf_refs) == len(set(inf_refs))
    image_ref_set = set(refs)
    for item in inferences:
        assert item["image_ref"] in image_ref_set
