"""Model-version use cases (REQ-F-MDL-001〜009). HTTP-free."""

from __future__ import annotations

import uuid
from pathlib import Path

from faunalab.ml.baseline import BaselineInspection
from faunalab.ml.metrics import Metrics, compute_metrics
from faunalab.ml.predict import load_onnx_session, predict_class_ids
from faunalab.ml.trained import (
    infer_trained_paths,
    is_embedding_head,
    load_trained_session,
)
from faunalab.persist.files import resolve_under
from faunalab.persist.store import ImageRow, ModelRow, Store

TRAINED_ONNX_NAME = "model.onnx"


class ModelNotFoundError(Exception):
    """The requested model ref is missing or logically deleted."""


class ModelNotDeletableError(Exception):
    """Active model or version 0 cannot be deleted (REQ-F-MDL-006)."""


class EmptyTestSplitError(Exception):
    """Re-evaluation requires at least one labeled test image (REQ-F-MDL-009)."""


class BaselineUnavailableError(Exception):
    """Version 0 evaluation needs a validated baseline asset."""


class ModelArtifactMissingError(Exception):
    """Trained-model evaluate expected an ONNX under artifact_dir."""


def should_auto_activate(active: ModelRow | None) -> bool:
    """REQ-F-MDL-004: first trained version activates if none or builtin is active.

    F014 must call `register_trained_model` on training success. This function
    is the contract; do not duplicate the rule in the job worker.
    """

    return active is None or active.builtin


def trained_artifact_relpath(version: int) -> str:
    return f"models/{version}"


def register_trained_model(
    store: Store,
    *,
    ref: str | None = None,
    created_at: str,
    metrics: Metrics | None = None,
    artifact_bytes: bytes | None = None,
) -> ModelRow:
    """Insert the next trained version (1, 2, …; never reused).

    Metrics stay `null` when the caller does not pass them. Pass
    `artifact_bytes` to write `model.onnx` before the row is visible.
    Training jobs should use `Store.complete_training_success` so cancel
    and SUCCEEDED share that lock. An empty test split is success with
    `metrics=null` (REQ-F-MDL-002).
    """

    return store.insert_trained_model(
        ref=ref or str(uuid.uuid4()),
        created_at=created_at,
        metrics=metrics,
        artifact_bytes=artifact_bytes,
    )


def activate_model(store: Store, ref: str) -> ModelRow:
    row = store.activate_model(ref)
    if row is None:
        raise ModelNotFoundError(ref)
    return row


def delete_model(store: Store, ref: str) -> None:
    """Remove artifacts; keep a tombstone so version numbers are not reused.

    Inference rows keep `model_id` (REQ-F-MDL-007). The model disappears
    from `_state` and GET. Check, artifact removal, and the tombstone share
    the store lock with activate so an in-flight activate cannot leave an
    active row without files.
    """

    outcome = store.purge_trained_model(ref)
    if outcome == "not_found":
        raise ModelNotFoundError(ref)
    if outcome == "not_deletable":
        raise ModelNotDeletableError(ref)


def evaluate_model(
    store: Store,
    ref: str,
    *,
    baseline: BaselineInspection,
) -> ModelRow:
    """Score the current labeled test split and persist metrics (REQ-F-MDL-009)."""

    model = store.get_model(ref)
    if model is None:
        raise ModelNotFoundError(ref)
    samples = store.list_labeled_test_images()
    if not samples:
        raise EmptyTestSplitError
    predicted = _predict_split(store, model, samples, baseline=baseline)
    truth: list[str] = []
    for item in samples:
        if item.label_class_id is None:
            raise EmptyTestSplitError
        truth.append(item.label_class_id)
    metrics = compute_metrics(truth, predicted)
    updated = store.update_metrics(ref, metrics)
    if updated is None:
        raise ModelNotFoundError(ref)
    return updated


def _predict_split(
    store: Store,
    model: ModelRow,
    samples: list[ImageRow],
    *,
    baseline: BaselineInspection,
) -> list[str]:
    paths = [_image_abs_path(store, item.path) for item in samples]
    if model.builtin:
        if not baseline.ok or baseline.model_path is None or baseline.class_map is None:
            raise BaselineUnavailableError
        session = load_onnx_session(baseline.model_path)
        return predict_class_ids(
            session,
            paths,
            builtin=True,
            class_map=baseline.class_map,
        )
    onnx_path = _trained_onnx_path(store, model)
    session = load_trained_session(onnx_path)
    embedding_session = None
    if is_embedding_head(session):
        if not baseline.ok or baseline.model_path is None:
            raise BaselineUnavailableError
        embedding_session = load_onnx_session(baseline.model_path)
    return infer_trained_paths(session, paths, embedding_session=embedding_session)


def _trained_onnx_path(store: Store, model: ModelRow) -> Path:
    relative = model.artifact_dir or trained_artifact_relpath(model.version)
    try:
        directory = resolve_under(store.data_dir, relative)
    except ValueError as exc:
        raise ModelArtifactMissingError(model.ref) from exc
    path = directory / TRAINED_ONNX_NAME
    if not path.is_file():
        raise ModelArtifactMissingError(model.ref)
    return path


def _image_abs_path(store: Store, relative: str) -> Path:
    return resolve_under(store.data_dir, relative)
