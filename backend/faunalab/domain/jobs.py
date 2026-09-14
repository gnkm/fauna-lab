"""Training-job use cases (REQ-F-TRN-001〜017). HTTP-free."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from faunalab.ml.baseline import BaselineInspection
from faunalab.persist.store import Store

DEFAULT_EPOCHS = 10
DEFAULT_BATCH_SIZE = 32
DEFAULT_LEARNING_RATE = 0.001
DEFAULT_SEED = 42
DEFAULT_AUGMENTATION = True
DEFAULT_USE_BASELINE = True

MAX_EPOCHS = 1000
MAX_BATCH_SIZE = 512

MIN_TRAIN_WITH_BASELINE = 10
MIN_TRAIN_WITHOUT_BASELINE = 50
MIN_VAL = 1
MIN_TRAIN_CLASSES = 2

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELED"})


class TrainingPreconditionError(Exception):
    """REQ-F-TRN-004 is not met."""


class BaselineUnavailableError(Exception):
    """use_baseline is set but baseline assets cannot be used (REQ-F-TRN-003)."""


class JobNotFoundError(Exception):
    """The requested job ref does not exist."""


class JobNotCancelableError(Exception):
    """Terminal jobs cannot be canceled (REQ-F-TRN-007)."""


class JobCanceled(Exception):
    """Cooperative cancel observed in the worker loop."""


@dataclass(frozen=True, slots=True)
class JobParams:
    epochs: int = DEFAULT_EPOCHS
    batch_size: int = DEFAULT_BATCH_SIZE
    learning_rate: float = DEFAULT_LEARNING_RATE
    seed: int = DEFAULT_SEED
    augmentation: bool = DEFAULT_AUGMENTATION
    use_baseline: bool = DEFAULT_USE_BASELINE

    def to_json(self) -> str:
        return json.dumps(
            {
                "epochs": self.epochs,
                "batch_size": self.batch_size,
                "learning_rate": self.learning_rate,
                "seed": self.seed,
                "augmentation": self.augmentation,
                "use_baseline": self.use_baseline,
            }
        )

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> JobParams:
        if not raw:
            return cls()
        return cls(
            epochs=int(raw.get("epochs", DEFAULT_EPOCHS)),
            batch_size=int(raw.get("batch_size", DEFAULT_BATCH_SIZE)),
            learning_rate=float(raw.get("learning_rate", DEFAULT_LEARNING_RATE)),
            seed=int(raw.get("seed", DEFAULT_SEED)),
            augmentation=bool(raw.get("augmentation", DEFAULT_AUGMENTATION)),
            use_baseline=bool(raw.get("use_baseline", DEFAULT_USE_BASELINE)),
        )


def min_train_count(*, use_baseline: bool) -> int:
    if use_baseline:
        return MIN_TRAIN_WITH_BASELINE
    return MIN_TRAIN_WITHOUT_BASELINE


def check_start_preconditions(
    store: Store,
    params: JobParams,
    *,
    baseline: BaselineInspection,
) -> None:
    """Raise if the job must not be queued (REQ-F-TRN-003 / 004)."""

    if params.use_baseline and not baseline.ok:
        raise BaselineUnavailableError
    stats = store.labeled_split_counts()
    train_n = stats["train"]
    val_n = stats["val"]
    train_classes = stats["train_classes"]
    needed = min_train_count(use_baseline=params.use_baseline)
    if train_n < needed or val_n < MIN_VAL or train_classes < MIN_TRAIN_CLASSES:
        raise TrainingPreconditionError


def enqueue_job(
    store: Store,
    params: JobParams,
    *,
    created_at: str,
    baseline: BaselineInspection,
    ref: str | None = None,
) -> str:
    """Insert QUEUED and return immediately. Does not wait for training."""

    check_start_preconditions(store, params, baseline=baseline)
    job_ref = ref or str(uuid.uuid4())
    store.insert_job(
        ref=job_ref,
        total_epochs=params.epochs,
        params_json=params.to_json(),
        created_at=created_at,
    )
    return job_ref


def request_cancel(store: Store, ref: str) -> str:
    """Cancel QUEUED immediately or flag RUNNING. Returns the resulting status."""

    outcome = store.request_cancel(ref)
    if outcome == "not_found":
        raise JobNotFoundError(ref)
    if outcome == "not_cancelable":
        raise JobNotCancelableError(ref)
    row = store.get_job(ref)
    if row is None:
        raise JobNotFoundError(ref)
    return row.status
