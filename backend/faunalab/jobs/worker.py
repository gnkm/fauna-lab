"""Training worker process. Uses NumPy; does not import PyTorch."""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from faunalab.domain.jobs import JobCanceled, JobParams
from faunalab.domain.models import TRAINED_ONNX_NAME, register_trained_model
from faunalab.ml.baseline import inspect_baseline_assets
from faunalab.ml.metrics import compute_metrics
from faunalab.ml.predict import load_onnx_session
from faunalab.ml.train import train_baseline_head, train_tiny_cnn
from faunalab.ml.trained import (
    infer_trained_paths,
    is_embedding_head,
    load_trained_session,
)
from faunalab.persist.files import remove_tree_if_present, resolve_under, write_bytes
from faunalab.persist.store import ImageRow, Store

LOGGER = logging.getLogger("faunalab.jobs.worker")
POLL_SECONDS = 0.2


def _utc_now_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print(
            "usage: python -m faunalab.jobs.worker DATA_DIR ASSETS_DIR",
            file=sys.stderr,
        )
        return 2
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    data_dir = Path(args[0])
    assets_dir = Path(args[1])
    store = Store(data_dir)
    store.open_existing()
    inspection = inspect_baseline_assets(assets_dir)
    try:
        while True:
            job = store.claim_next_queued()
            if job is None:
                time.sleep(POLL_SECONDS)
                continue
            try:
                _run_claimed(store, job.ref, inspection.model_path)
            except JobCanceled:
                store.mark_canceled(job.ref)
            except Exception:
                LOGGER.exception("training job %s failed", job.ref)
                store.fail_job(job.ref, "学習中に予期しない誤りが起きました。")
            finally:
                remove_tree_if_present(store.data_dir, f"jobs/{job.ref}/work")
    finally:
        store.close()
    return 0


def _run_claimed(
    store: Store,
    ref: str,
    baseline_path: Path | None,
) -> None:
    record = store.get_job(ref)
    if record is None:
        return
    params = JobParams.from_mapping(record.params)
    if store.is_cancel_requested(ref):
        raise JobCanceled
    train_rows = store.list_labeled_split("train")
    val_rows = store.list_labeled_split("val")
    train_images, train_labels = _open_rows(store, train_rows)
    val_images, val_labels = _open_rows(store, val_rows)
    work_rel = f"jobs/{ref}/work"
    dest = resolve_under(store.data_dir, f"{work_rel}/{TRAINED_ONNX_NAME}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    def should_cancel() -> bool:
        return store.is_cancel_requested(ref)

    def on_epoch(
        epoch: int,
        train_loss: float,
        val_loss: float,
        val_accuracy: float,
        duration: float,
    ) -> None:
        if should_cancel():
            raise JobCanceled
        store.record_epoch(
            ref,
            epoch=epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            val_accuracy=val_accuracy,
            duration_seconds=duration,
            created_at=_utc_now_z(),
        )

    try:
        if params.use_baseline:
            if baseline_path is None or not baseline_path.is_file():
                store.fail_job(ref, "ベースライン資産を利用できません。")
                return
            train_baseline_head(
                train_images=train_images,
                train_labels=train_labels,
                val_images=val_images,
                val_labels=val_labels,
                params=params,
                baseline_path=baseline_path,
                dest=dest,
                should_cancel=should_cancel,
                on_epoch=on_epoch,
            )
        else:
            train_tiny_cnn(
                train_images=train_images,
                train_labels=train_labels,
                val_images=val_images,
                val_labels=val_labels,
                params=params,
                dest=dest,
                should_cancel=should_cancel,
                on_epoch=on_epoch,
            )
        if should_cancel():
            raise JobCanceled
        metrics = _maybe_test_metrics(store, dest, baseline_path)
        if should_cancel():
            raise JobCanceled
        created = register_trained_model(
            store, created_at=_utc_now_z(), metrics=metrics
        )
        artifact_dir = created.artifact_dir or f"models/{created.version}"
        write_bytes(
            store.data_dir,
            f"{artifact_dir}/{TRAINED_ONNX_NAME}",
            dest.read_bytes(),
        )
        store.succeed_job(ref, created.ref)
    finally:
        for image in train_images + val_images:
            image.close()


def _open_rows(
    store: Store, rows: list[ImageRow]
) -> tuple[list[Image.Image], list[str]]:
    images: list[Image.Image] = []
    labels: list[str] = []
    for row in rows:
        if row.label_class_id is None:
            continue
        path = resolve_under(store.data_dir, row.path)
        with Image.open(path) as image:
            image.load()
            images.append(image.copy())
        labels.append(row.label_class_id)
    return images, labels


def _maybe_test_metrics(
    store: Store, onnx_path: Path, baseline_path: Path | None
) -> dict[str, object] | None:
    samples = store.list_labeled_test_images()
    if not samples:
        return None
    session = load_trained_session(onnx_path)
    embedding_session = None
    if is_embedding_head(session):
        if baseline_path is None:
            raise RuntimeError("embedding-head model needs baseline weights")
        embedding_session = load_onnx_session(baseline_path)
    paths = [resolve_under(store.data_dir, row.path) for row in samples]
    truth = [row.label_class_id for row in samples if row.label_class_id is not None]
    predicted = infer_trained_paths(session, paths, embedding_session=embedding_session)
    return compute_metrics(truth, predicted)


if __name__ == "__main__":
    raise SystemExit(main())
