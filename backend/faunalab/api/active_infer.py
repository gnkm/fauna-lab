"""Score images with the active model (baseline or trained ONNX)."""

from __future__ import annotations

from fastapi import Request
from PIL import Image

from faunalab.api.errors import baseline_unavailable, error_for_code, no_active_model
from faunalab.domain.models import TRAINED_ONNX_NAME
from faunalab.ml.fold import FoldResult
from faunalab.ml.runtime import BaselineRuntime
from faunalab.ml.session_cache import OnnxSessionCache
from faunalab.ml.trained import infer_trained_images, is_embedding_head
from faunalab.persist.files import resolve_under
from faunalab.persist.store import ModelRow, Store


def require_active_model(store: Store) -> ModelRow:
    model = store.get_active_model()
    if model is None:
        raise no_active_model()
    return model


def infer_images_for_model(
    request: Request,
    store: Store,
    model: ModelRow,
    images: list[Image.Image],
) -> list[FoldResult]:
    if model.builtin:
        runtime = getattr(request.app.state, "baseline_runtime", None)
        if not isinstance(runtime, BaselineRuntime):
            raise baseline_unavailable()
        return runtime.infer_images(images)
    return _infer_trained_model(store, model, images, request)


def _session_cache(request: Request) -> OnnxSessionCache:
    cache = getattr(request.app.state, "onnx_sessions", None)
    if isinstance(cache, OnnxSessionCache):
        return cache
    cache = OnnxSessionCache()
    request.app.state.onnx_sessions = cache
    return cache


def _infer_trained_model(
    store: Store,
    model: ModelRow,
    images: list[Image.Image],
    request: Request,
) -> list[FoldResult]:
    relative = model.artifact_dir or f"models/{model.version}"
    try:
        directory = resolve_under(store.data_dir, relative)
    except ValueError as exc:
        raise error_for_code(
            "internal_error",
            "モデル成果物を読み込めません。",
        ) from exc
    onnx_path = directory / TRAINED_ONNX_NAME
    if not onnx_path.is_file():
        raise error_for_code(
            "internal_error",
            "モデル成果物を読み込めません。",
        )
    session = _session_cache(request).get(onnx_path)
    embedding_session = None
    if is_embedding_head(session):
        runtime = getattr(request.app.state, "baseline_runtime", None)
        if not isinstance(runtime, BaselineRuntime):
            raise baseline_unavailable()
        embedding_session = runtime.locked_session()
    return infer_trained_images(session, images, embedding_session=embedding_session)
