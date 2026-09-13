"""SQLite store under FAUNALAB_DATA_DIR (REQ-DATA-011, REQ-F-SYS-002)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from faunalab.domain.classes import CLASS_IDS, SPLIT_IDS, SYSTEM_CLASSES
from faunalab.persist.files import (
    ensure_dir,
    remove_tree_if_present,
    write_bytes,
)
from faunalab.persist.schema import SCHEMA_SQL, SCHEMA_VERSION

IN_QUERY_CHUNK = 500
TRAINED_ONNX_NAME = "model.onnx"

LOGGER = logging.getLogger("faunalab.persist")

DATA_SUBDIRS: tuple[str, ...] = ("images", "thumbs", "models", "jobs")
DB_FILENAME = "db.sqlite3"

_MODEL_SELECT = """
SELECT ref, version, builtin, active, metrics_json, artifact_dir, created_at
FROM models
"""

_IMAGE_SELECT = """
SELECT
    i.ref AS ref,
    i.sha256 AS sha256,
    i.split AS split,
    i.created_at AS created_at,
    i.original_name AS original_name,
    i.size_bytes AS size_bytes,
    i.width AS width,
    i.height AS height,
    i.path AS path,
    l.class_id AS label_class_id,
    l.source AS label_source,
    s.class_id AS suggestion_class_id,
    s.confidence AS suggestion_confidence,
    m.ref AS suggestion_model_ref
FROM images AS i
LEFT JOIN labels AS l ON l.image_id = i.id
LEFT JOIN suggestions AS s ON s.image_id = i.id
LEFT JOIN models AS m ON m.id = s.model_id
"""


@dataclass(frozen=True, slots=True)
class ClassRow:
    class_id: str
    display_name: str
    display_order: int


class DuplicateImageError(Exception):
    """SHA-256 uniqueness violation (REQ-F-IMG-006 / REQ-DATA-003)."""


class ModelNotFoundError(Exception):
    """A referenced model ref does not exist."""


class ImageNotFoundError(Exception):
    """A referenced image ref does not exist."""


class SuggestionNotFoundError(Exception):
    """A referenced suggestion does not exist."""


@dataclass(frozen=True, slots=True)
class ImageRow:
    ref: str
    sha256: str
    split: str
    label_class_id: str | None
    label_source: str | None
    suggestion_class_id: str | None
    suggestion_confidence: float | None
    suggestion_model_ref: str | None
    created_at: str
    original_name: str = ""
    size_bytes: int = 0
    width: int | None = None
    height: int | None = None
    path: str = ""


@dataclass(frozen=True, slots=True)
class JobRow:
    ref: str
    status: str
    current_epoch: int
    total_epochs: int
    model_ref: str | None
    created_at: str
    params: Any = None
    failed_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelRow:
    ref: str
    version: int
    builtin: bool
    active: bool
    metrics: Any
    created_at: str
    artifact_dir: str | None = None


@dataclass(frozen=True, slots=True)
class InferenceRow:
    ref: str
    image_ref: str
    model_ref: str
    top_class_id: str
    top_confidence: float
    other_mass: float | None
    low_confidence: bool
    scores: Any
    created_at: str


@dataclass(frozen=True, slots=True)
class InferenceNew:
    ref: str
    image_ref: str
    top_class_id: str
    top_confidence: float
    other_mass: float | None
    low_confidence: bool
    scores: list[dict[str, Any]]
    created_at: str
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SuggestionRow:
    image_ref: str
    class_id: str
    confidence: float
    model_ref: str


@dataclass(frozen=True, slots=True)
class SuggestionNew:
    image_ref: str
    class_id: str
    confidence: float
    created_at: str


class Store:
    """Process-local SQLite connection. Writes stay under `data_dir`."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_path = data_dir / DB_FILENAME
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create the data directory layout, schema, and seed 8 classes."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for name in DATA_SUBDIRS:
            (self.data_dir / name).mkdir(exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            self._conn = conn
            with conn:
                conn.executescript(SCHEMA_SQL)
                self._ensure_model_deleted_column(conn)
                current = conn.execute("PRAGMA user_version").fetchone()
                version = int(current[0]) if current is not None else 0
                if version > SCHEMA_VERSION:
                    LOGGER.warning(
                        "database schema version %s is newer than code %s",
                        version,
                        SCHEMA_VERSION,
                    )
                elif version < SCHEMA_VERSION:
                    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._seed_classes(conn)
                self._ensure_job_cancel_column(conn)
                self._recover_interrupted_jobs(conn)

    def fail_interrupted_jobs(self) -> None:
        """Mark leftover RUNNING jobs FAILED. Safe for a respawned worker."""

        with self._locked() as conn:
            with conn:
                self._recover_interrupted_jobs(conn)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def open_existing(self) -> None:
        """Connect for the worker. Do not seed or recover (API already did)."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            self._conn = conn

    @contextmanager
    def _locked(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._conn is None:
                raise RuntimeError("store is not initialized")
            yield self._conn

    def _seed_classes(self, conn: sqlite3.Connection) -> None:
        for spec in SYSTEM_CLASSES:
            conn.execute(
                """
                INSERT INTO classes (class_id, display_name, display_order)
                VALUES (?, ?, ?)
                ON CONFLICT(class_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    display_order = excluded.display_order
                """,
                (spec.class_id, spec.display_name, spec.display_order),
            )

    def _recover_interrupted_jobs(self, conn: sqlite3.Connection) -> None:
        # REQ-F-TRN-014 / DESIGN 5.5: 起動時に残存 RUNNING を FAILED へ。
        rows = conn.execute("SELECT ref FROM jobs WHERE status = 'RUNNING'").fetchall()
        conn.execute(
            """
            UPDATE jobs
            SET status = 'FAILED',
                failed_reason = 'プロセス中断',
                finished_at = ?
            WHERE status = 'RUNNING'
            """,
            (_utc_now_z(),),
        )
        for row in rows:
            remove_tree_if_present(self.data_dir, f"jobs/{row['ref']}/work")

    def _ensure_job_cancel_column(self, conn: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(jobs)")}
        if "cancel_requested" not in columns:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL "
                "DEFAULT 0 CHECK (cancel_requested IN (0, 1))"
            )

    def _ensure_model_deleted_column(self, conn: sqlite3.Connection) -> None:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(models)")}
        if "deleted" not in columns:
            conn.execute(
                "ALTER TABLE models ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0 "
                "CHECK (deleted IN (0, 1))"
            )

    def list_classes(self) -> list[ClassRow]:
        with self._locked() as conn:
            rows = conn.execute(
                """
                SELECT class_id, display_name, display_order
                FROM classes
                ORDER BY display_order ASC, class_id ASC
                """
            ).fetchall()
        return [
            ClassRow(
                class_id=row["class_id"],
                display_name=row["display_name"],
                display_order=int(row["display_order"]),
            )
            for row in rows
        ]

    def list_images(self) -> list[ImageRow]:
        with self._locked() as conn:
            rows = conn.execute(
                f"{_IMAGE_SELECT} ORDER BY i.created_at ASC, i.ref ASC"
            ).fetchall()
        return [_image_row(row) for row in rows]

    def get_image(self, ref: str) -> ImageRow | None:
        with self._locked() as conn:
            row = conn.execute(
                f"{_IMAGE_SELECT} WHERE i.ref = ?",
                (ref,),
            ).fetchone()
        return None if row is None else _image_row(row)

    def get_image_by_sha256(self, sha256: str) -> ImageRow | None:
        with self._locked() as conn:
            row = conn.execute(
                f"{_IMAGE_SELECT} WHERE i.sha256 = ?",
                (sha256,),
            ).fetchone()
        return None if row is None else _image_row(row)

    def sha256_exists(self, sha256: str) -> bool:
        with self._locked() as conn:
            row = conn.execute(
                "SELECT 1 FROM images WHERE sha256 = ? LIMIT 1",
                (sha256,),
            ).fetchone()
        return row is not None

    def insert_image(
        self,
        *,
        ref: str,
        sha256: str,
        original_name: str,
        size_bytes: int,
        width: int,
        height: int,
        path: str,
        created_at: str,
    ) -> None:
        with self._locked() as conn:
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO images (
                            ref, sha256, original_name, size_bytes,
                            width, height, split, path, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 'unassigned', ?, ?)
                        """,
                        (
                            ref,
                            sha256,
                            original_name,
                            size_bytes,
                            width,
                            height,
                            path,
                            created_at,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                message = str(exc).lower()
                if "sha256" in message or "unique" in message:
                    raise DuplicateImageError from exc
                raise

    def delete_image(self, ref: str) -> ImageRow | None:
        existing = self.get_image(ref)
        if existing is None:
            return None
        with self._locked() as conn:
            with conn:
                conn.execute("DELETE FROM images WHERE ref = ?", (ref,))
        return existing

    def list_images_page(
        self,
        *,
        split: str | None,
        class_id: str | None,
        labeled: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ImageRow], int]:
        conditions: list[str] = []
        params: list[object] = []
        if split is not None:
            conditions.append("i.split = ?")
            params.append(split)
        if class_id is not None:
            conditions.append("l.class_id = ?")
            params.append(class_id)
        if labeled is True:
            conditions.append("l.image_id IS NOT NULL")
        elif labeled is False:
            conditions.append("l.image_id IS NULL")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_sql = (
            "SELECT COUNT(*) AS n FROM images AS i "
            f"LEFT JOIN labels AS l ON l.image_id = i.id {where}"
        )
        page_sql = (
            f"{_IMAGE_SELECT} {where} "
            "ORDER BY i.created_at ASC, i.ref ASC LIMIT ? OFFSET ?"
        )
        with self._locked() as conn:
            total = int(conn.execute(count_sql, params).fetchone()["n"])
            rows = conn.execute(page_sql, [*params, limit, offset]).fetchall()
        return [_image_row(row) for row in rows], total

    def get_label(self, ref: str) -> tuple[str, str, str] | None:
        with self._locked() as conn:
            row = conn.execute(
                """
                SELECT l.class_id AS class_id,
                       l.source AS source,
                       l.created_at AS created_at
                FROM images AS i
                JOIN labels AS l ON l.image_id = i.id
                WHERE i.ref = ?
                """,
                (ref,),
            ).fetchone()
        if row is None:
            return None
        return str(row["class_id"]), str(row["source"]), str(row["created_at"])

    def upsert_label(
        self, ref: str, class_id: str, source: str, assigned_at: str
    ) -> bool:
        with self._locked() as conn:
            with conn:
                row = conn.execute(
                    "SELECT id FROM images WHERE ref = ?",
                    (ref,),
                ).fetchone()
                if row is None:
                    return False
                _upsert_label_row(conn, int(row["id"]), class_id, source, assigned_at)
        return True

    def upsert_labels_bulk(
        self, refs: list[str], class_id: str, source: str, assigned_at: str
    ) -> int:
        unique = list(dict.fromkeys(refs))
        with self._locked() as conn:
            with conn:
                id_by_ref = _image_ids_by_refs(conn, unique)
                if len(id_by_ref) != len(unique):
                    raise ImageNotFoundError
                for ref in unique:
                    _upsert_label_row(
                        conn, id_by_ref[ref], class_id, source, assigned_at
                    )
        return len(unique)

    def delete_label(self, ref: str) -> bool | None:
        """None if the image is missing. True if unlabeled (already or now)."""

        with self._locked() as conn:
            with conn:
                row = conn.execute(
                    "SELECT id FROM images WHERE ref = ?",
                    (ref,),
                ).fetchone()
                if row is None:
                    return None
                image_id = int(row["id"])
                conn.execute("DELETE FROM labels WHERE image_id = ?", (image_id,))
                conn.execute(
                    "UPDATE images SET split = 'unassigned' WHERE id = ?",
                    (image_id,),
                )
        return True

    def list_labeled(self) -> list[tuple[str, str]]:
        with self._locked() as conn:
            rows = conn.execute(
                """
                SELECT i.ref AS ref, l.class_id AS class_id
                FROM images AS i
                JOIN labels AS l ON l.image_id = i.id
                ORDER BY i.ref ASC
                """
            ).fetchall()
        return [(str(row["ref"]), str(row["class_id"])) for row in rows]

    def list_labeled_test_images(self) -> list[ImageRow]:
        with self._locked() as conn:
            rows = conn.execute(
                f"{_IMAGE_SELECT} WHERE i.split = 'test' AND l.class_id IS NOT NULL "
                "ORDER BY i.created_at ASC, i.ref ASC"
            ).fetchall()
        return [_image_row(row) for row in rows]

    def apply_split_assignments(self, assignments: dict[str, str]) -> tuple[int, int]:
        with self._locked() as conn:
            with conn:
                return _apply_split_assignments(conn, assignments)

    def recompute_splits(
        self, assign: Callable[[list[tuple[str, str]]], dict[str, str]]
    ) -> tuple[int, int]:
        """List labeled images and apply assignments in one lock (no TOCTOU)."""

        with self._locked() as conn:
            with conn:
                labeled = [
                    (str(row["ref"]), str(row["class_id"]))
                    for row in conn.execute(
                        """
                        SELECT i.ref AS ref, l.class_id AS class_id
                        FROM images AS i
                        JOIN labels AS l ON l.image_id = i.id
                        ORDER BY i.ref ASC
                        """
                    )
                ]
                return _apply_split_assignments(conn, assign(labeled))

    def stats(self) -> dict[str, object]:
        with self._locked() as conn:
            image_count = int(
                conn.execute("SELECT COUNT(*) AS n FROM images").fetchone()["n"]
            )
            labeled_count = int(
                conn.execute("SELECT COUNT(*) AS n FROM labels").fetchone()["n"]
            )
            suggestion_count = int(
                conn.execute("SELECT COUNT(*) AS n FROM suggestions").fetchone()["n"]
            )
            per_class = {class_id: 0 for class_id in CLASS_IDS}
            for row in conn.execute(
                "SELECT class_id, COUNT(*) AS n FROM labels GROUP BY class_id"
            ):
                per_class[str(row["class_id"])] = int(row["n"])
            per_split = {split: 0 for split in SPLIT_IDS}
            for row in conn.execute(
                "SELECT split, COUNT(*) AS n FROM images GROUP BY split"
            ):
                per_split[str(row["split"])] = int(row["n"])
            active = conn.execute(
                """
                SELECT ref, version, builtin
                FROM models
                WHERE active = 1
                LIMIT 1
                """
            ).fetchone()
            baseline = conn.execute(
                """
                SELECT 1 AS n
                FROM models
                WHERE version = 0 AND builtin = 1
                LIMIT 1
                """
            ).fetchone()
            job = conn.execute(
                """
                SELECT 1 AS n FROM jobs
                WHERE status IN ('QUEUED', 'RUNNING')
                LIMIT 1
                """
            ).fetchone()
        active_model = None
        if active is not None:
            active_model = {
                "ref": str(active["ref"]),
                "version": int(active["version"]),
                "builtin": bool(active["builtin"]),
            }
        return {
            "image_count": image_count,
            "labeled_count": labeled_count,
            "unlabeled_count": image_count - labeled_count,
            "suggestion_count": suggestion_count,
            "per_class": per_class,
            "per_split": per_split,
            "active_model_ref": None if active_model is None else active_model["ref"],
            "active_model": active_model,
            "baseline_registered": baseline is not None,
            "has_active_job": job is not None,
        }

    def list_jobs(self) -> list[JobRow]:
        with self._locked() as conn:
            rows = conn.execute(
                """
                SELECT
                    j.ref AS ref,
                    j.status AS status,
                    j.current_epoch AS current_epoch,
                    j.total_epochs AS total_epochs,
                    m.ref AS model_ref,
                    j.created_at AS created_at,
                    j.params_json AS params_json,
                    j.failed_reason AS failed_reason
                FROM jobs AS j
                LEFT JOIN models AS m ON m.id = j.model_id
                ORDER BY j.created_at ASC, j.ref ASC
                """
            ).fetchall()
        return [_job_row(row) for row in rows]

    def list_jobs_page(self, *, limit: int, offset: int) -> tuple[list[JobRow], int]:
        with self._locked() as conn:
            total = int(conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"])
            query = (
                f"{_JOB_SELECT} ORDER BY j.created_at DESC, j.ref DESC LIMIT ? OFFSET ?"
            )
            rows = conn.execute(query, (limit, offset)).fetchall()
        return [_job_row(row) for row in rows], total

    def get_job(self, ref: str) -> JobRow | None:
        with self._locked() as conn:
            row = conn.execute(f"{_JOB_SELECT} WHERE j.ref = ?", (ref,)).fetchone()
        return None if row is None else _job_row(row)

    def insert_job(
        self,
        *,
        ref: str,
        total_epochs: int,
        params_json: str,
        created_at: str,
    ) -> None:
        with self._locked() as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        ref, status, current_epoch, total_epochs,
                        params_json, created_at
                    )
                    VALUES (?, 'QUEUED', 0, ?, ?, ?)
                    """,
                    (ref, total_epochs, params_json, created_at),
                )

    def labeled_split_counts(self) -> dict[str, int]:
        with self._locked() as conn:
            train_n = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM images AS i
                    JOIN labels AS l ON l.image_id = i.id
                    WHERE i.split = 'train'
                    """
                ).fetchone()["n"]
            )
            val_n = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM images AS i
                    JOIN labels AS l ON l.image_id = i.id
                    WHERE i.split = 'val'
                    """
                ).fetchone()["n"]
            )
            train_classes = int(
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT l.class_id) AS n
                    FROM images AS i
                    JOIN labels AS l ON l.image_id = i.id
                    WHERE i.split = 'train'
                    """
                ).fetchone()["n"]
            )
        return {
            "train": train_n,
            "val": val_n,
            "train_classes": train_classes,
        }

    def list_labeled_split(self, split: str) -> list[ImageRow]:
        with self._locked() as conn:
            rows = conn.execute(
                f"{_IMAGE_SELECT} WHERE i.split = ? AND l.class_id IS NOT NULL "
                "ORDER BY i.created_at ASC, i.ref ASC",
                (split,),
            ).fetchall()
        return [_image_row(row) for row in rows]

    def claim_next_queued(self) -> JobRow | None:
        started = _utc_now_z()
        claimed_ref: str | None = None
        with self._locked() as conn:
            with conn:
                running = conn.execute(
                    "SELECT 1 AS n FROM jobs WHERE status = 'RUNNING' LIMIT 1"
                ).fetchone()
                if running is not None:
                    return None
                queued = conn.execute(
                    """
                    SELECT ref FROM jobs
                    WHERE status = 'QUEUED'
                    ORDER BY created_at ASC, ref ASC
                    LIMIT 1
                    """
                ).fetchone()
                if queued is None:
                    return None
                claimed_ref = str(queued["ref"])
                try:
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'RUNNING', started_at = ?
                        WHERE ref = ? AND status = 'QUEUED'
                        """,
                        (started, claimed_ref),
                    )
                except sqlite3.IntegrityError:
                    return None
        if claimed_ref is None:
            return None
        return self.get_job(claimed_ref)

    def request_cancel(
        self, ref: str
    ) -> Literal["canceled", "requested", "not_cancelable", "not_found"]:
        now = _utc_now_z()
        with self._locked() as conn:
            with conn:
                row = conn.execute(
                    "SELECT status FROM jobs WHERE ref = ?",
                    (ref,),
                ).fetchone()
                if row is None:
                    return "not_found"
                status = str(row["status"])
                if status == "QUEUED":
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'CANCELED',
                            cancel_requested = 1,
                            finished_at = ?
                        WHERE ref = ? AND status = 'QUEUED'
                        """,
                        (now, ref),
                    )
                    return "canceled"
                if status == "RUNNING":
                    conn.execute(
                        """
                        UPDATE jobs
                        SET cancel_requested = 1
                        WHERE ref = ? AND status = 'RUNNING'
                        """,
                        (ref,),
                    )
                    return "requested"
                return "not_cancelable"

    def is_cancel_requested(self, ref: str) -> bool:
        with self._locked() as conn:
            row = conn.execute(
                "SELECT cancel_requested FROM jobs WHERE ref = ?",
                (ref,),
            ).fetchone()
        return row is not None and int(row["cancel_requested"]) == 1

    def mark_canceled(self, ref: str) -> None:
        now = _utc_now_z()
        with self._locked() as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'CANCELED', finished_at = ?
                    WHERE ref = ? AND status IN ('QUEUED', 'RUNNING')
                    """,
                    (now, ref),
                )

    def fail_job(self, ref: str, reason: str) -> None:
        now = _utc_now_z()
        with self._locked() as conn:
            with conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'FAILED',
                        failed_reason = ?,
                        finished_at = ?
                    WHERE ref = ? AND status = 'RUNNING'
                    """,
                    (reason, now, ref),
                )

    def succeed_job(self, ref: str, model_ref: str) -> bool:
        now = _utc_now_z()
        with self._locked() as conn:
            with conn:
                model = conn.execute(
                    "SELECT id FROM models WHERE ref = ? AND deleted = 0",
                    (model_ref,),
                ).fetchone()
                if model is None:
                    raise RuntimeError(f"model {model_ref} missing at job success")
                cursor = conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'SUCCEEDED',
                        model_id = ?,
                        finished_at = ?
                    WHERE ref = ?
                      AND status = 'RUNNING'
                      AND cancel_requested = 0
                    """,
                    (int(model["id"]), now, ref),
                )
                return cursor.rowcount == 1

    def complete_training_success(
        self,
        ref: str,
        *,
        artifact_bytes: bytes,
        metrics: Any,
        created_at: str,
        model_ref: str | None = None,
    ) -> Literal["succeeded", "canceled"]:
        """Register the trained model, write ONNX, and succeed the job.

        Cancel, artifact write, INSERT, and SUCCEEDED share one lock so a
        first trained version cannot become active without `model.onnx`, and
        a late cancel cannot lose to SUCCEEDED.
        """

        now = _utc_now_z()
        created_dir: str | None = None
        try:
            with self._locked() as conn:
                with conn:
                    row = conn.execute(
                        """
                        SELECT status, cancel_requested FROM jobs WHERE ref = ?
                        """,
                        (ref,),
                    ).fetchone()
                    if row is None or str(row["status"]) != "RUNNING":
                        return "canceled"
                    if int(row["cancel_requested"]) == 1:
                        conn.execute(
                            """
                            UPDATE jobs
                            SET status = 'CANCELED', finished_at = ?
                            WHERE ref = ? AND status = 'RUNNING'
                            """,
                            (now, ref),
                        )
                        return "canceled"
                    new_ref = model_ref or str(uuid.uuid4())
                    created_dir = self._insert_trained_model_locked(
                        conn,
                        ref=new_ref,
                        created_at=created_at,
                        metrics=metrics,
                        artifact_bytes=artifact_bytes,
                    )
                    model = conn.execute(
                        "SELECT id FROM models WHERE ref = ? AND deleted = 0",
                        (new_ref,),
                    ).fetchone()
                    if model is None:
                        raise RuntimeError("trained model missing after insert")
                    conn.execute(
                        """
                        UPDATE jobs
                        SET status = 'SUCCEEDED',
                            model_id = ?,
                            finished_at = ?
                        WHERE ref = ? AND status = 'RUNNING'
                        """,
                        (int(model["id"]), now, ref),
                    )
        except Exception:
            if created_dir is not None:
                remove_tree_if_present(self.data_dir, created_dir)
            raise
        return "succeeded"

    def record_epoch(
        self,
        ref: str,
        *,
        epoch: int,
        train_loss: float,
        val_loss: float,
        val_accuracy: float,
        duration_seconds: float,
        created_at: str,
    ) -> None:
        payload = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "val_accuracy": val_accuracy,
            "duration_seconds": duration_seconds,
        }
        with self._locked() as conn:
            with conn:
                row = conn.execute(
                    "SELECT id FROM jobs WHERE ref = ?",
                    (ref,),
                ).fetchone()
                if row is None:
                    raise RuntimeError(f"job {ref} missing while recording epoch")
                conn.execute(
                    """
                    UPDATE jobs SET current_epoch = ?
                    WHERE ref = ? AND status = 'RUNNING'
                    """,
                    (epoch, ref),
                )
                conn.execute(
                    """
                    INSERT INTO job_epoch_logs (
                        job_id, epoch, train_loss, val_loss,
                        val_accuracy, duration_seconds, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(row["id"]),
                        epoch,
                        train_loss,
                        val_loss,
                        val_accuracy,
                        duration_seconds,
                        created_at,
                    ),
                )
        log_dir = ensure_dir(self.data_dir, f"jobs/{ref}")
        log_path = log_dir / "epochs.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def list_job_logs_page(
        self, ref: str, *, limit: int, offset: int
    ) -> tuple[list[dict[str, Any]], int]:
        with self._locked() as conn:
            job = conn.execute(
                "SELECT id FROM jobs WHERE ref = ?",
                (ref,),
            ).fetchone()
            if job is None:
                return [], 0
            job_id = int(job["id"])
            total = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM job_epoch_logs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()["n"]
            )
            rows = conn.execute(
                """
                SELECT epoch, train_loss, val_loss, val_accuracy, duration_seconds
                FROM job_epoch_logs
                WHERE job_id = ?
                ORDER BY epoch ASC
                LIMIT ? OFFSET ?
                """,
                (job_id, limit, offset),
            ).fetchall()
        items = [
            {
                "epoch": int(row["epoch"]),
                "train_loss": float(row["train_loss"]),
                "val_loss": float(row["val_loss"]),
                "val_accuracy": float(row["val_accuracy"]),
                "duration_seconds": float(row["duration_seconds"]),
            }
            for row in rows
        ]
        return items, total

    def list_models(self) -> list[ModelRow]:
        with self._locked() as conn:
            rows = conn.execute(
                f"{_MODEL_SELECT} WHERE deleted = 0 ORDER BY version ASC"
            ).fetchall()
        return [_model_row(row) for row in rows]

    def list_models_page(
        self, *, limit: int, offset: int
    ) -> tuple[list[ModelRow], int]:
        with self._locked() as conn:
            total = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM models WHERE deleted = 0"
                ).fetchone()["n"]
            )
            rows = conn.execute(
                f"{_MODEL_SELECT} WHERE deleted = 0 "
                "ORDER BY version DESC, ref DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_model_row(row) for row in rows], total

    def get_model(self, ref: str) -> ModelRow | None:
        with self._locked() as conn:
            row = conn.execute(
                f"{_MODEL_SELECT} WHERE ref = ? AND deleted = 0",
                (ref,),
            ).fetchone()
        return None if row is None else _model_row(row)

    def get_model_by_version(self, version: int) -> ModelRow | None:
        with self._locked() as conn:
            row = conn.execute(
                f"{_MODEL_SELECT} WHERE version = ? AND deleted = 0",
                (version,),
            ).fetchone()
        return None if row is None else _model_row(row)

    def get_active_model(self) -> ModelRow | None:
        with self._locked() as conn:
            row = conn.execute(
                f"{_MODEL_SELECT} WHERE active = 1 AND deleted = 0 LIMIT 1"
            ).fetchone()
        return None if row is None else _model_row(row)

    def ensure_builtin_model(self, *, ref: str, created_at: str) -> ModelRow:
        existing = self.get_model_by_version(0)
        if existing is not None:
            return existing
        with self._locked() as conn:
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO models (
                            ref, version, builtin, active,
                            metrics_json, artifact_dir, created_at, deleted
                        )
                        VALUES (?, 0, 1, 0, NULL, NULL, ?, 0)
                        """,
                        (ref, created_at),
                    )
            except sqlite3.IntegrityError:
                existing = self.get_model_by_version(0)
                if existing is not None:
                    return existing
                raise
        created = self.get_model_by_version(0)
        if created is None:
            raise RuntimeError("failed to persist builtin model version 0")
        return created

    def activate_if_none_active(self, version: int) -> None:
        with self._locked() as conn:
            with conn:
                row = conn.execute(
                    "SELECT 1 FROM models WHERE active = 1 AND deleted = 0 LIMIT 1"
                ).fetchone()
                if row is not None:
                    return
                conn.execute(
                    "UPDATE models SET active = 1 WHERE version = ? AND deleted = 0",
                    (version,),
                )

    def activate_model(self, ref: str) -> ModelRow | None:
        with self._locked() as conn:
            with conn:
                row = conn.execute(
                    f"{_MODEL_SELECT} WHERE ref = ? AND deleted = 0",
                    (ref,),
                ).fetchone()
                if row is None:
                    return None
                conn.execute("UPDATE models SET active = 0 WHERE active = 1")
                conn.execute(
                    "UPDATE models SET active = 1 WHERE ref = ? AND deleted = 0",
                    (ref,),
                )
        return self.get_model(ref)

    def insert_trained_model(
        self,
        *,
        ref: str,
        created_at: str,
        metrics: Any = None,
        artifact_bytes: bytes | None = None,
    ) -> ModelRow:
        """Allocate the next version, create its directory, then insert.

        Auto-activation (REQ-F-MDL-004) is decided in this same transaction.
        If the directory or artifact cannot be created, no row is written.
        """

        created_dir: str | None = None
        try:
            with self._locked() as conn:
                with conn:
                    created_dir = self._insert_trained_model_locked(
                        conn,
                        ref=ref,
                        created_at=created_at,
                        metrics=metrics,
                        artifact_bytes=artifact_bytes,
                    )
        except Exception:
            if created_dir is not None:
                remove_tree_if_present(self.data_dir, created_dir)
            raise
        created = self.get_model(ref)
        if created is None:
            raise RuntimeError("failed to persist trained model")
        return created

    def _insert_trained_model_locked(
        self,
        conn: sqlite3.Connection,
        *,
        ref: str,
        created_at: str,
        metrics: Any,
        artifact_bytes: bytes | None,
    ) -> str:
        metrics_json = None if metrics is None else json.dumps(metrics)
        max_row = conn.execute("SELECT MAX(version) AS m FROM models").fetchone()
        raw_max = max_row["m"] if max_row is not None else None
        version = max(1, (0 if raw_max is None else int(raw_max)) + 1)
        artifact_dir = f"models/{version}"
        ensure_dir(self.data_dir, artifact_dir)
        try:
            if artifact_bytes is not None:
                write_bytes(
                    self.data_dir,
                    f"{artifact_dir}/{TRAINED_ONNX_NAME}",
                    artifact_bytes,
                )
            active = conn.execute(
                f"{_MODEL_SELECT} WHERE active = 1 AND deleted = 0 LIMIT 1"
            ).fetchone()
            activate = active is None or bool(active["builtin"])
            if activate:
                conn.execute("UPDATE models SET active = 0 WHERE active = 1")
            conn.execute(
                """
                INSERT INTO models (
                    ref, version, builtin, active,
                    metrics_json, artifact_dir, created_at, deleted
                )
                VALUES (?, ?, 0, ?, ?, ?, ?, 0)
                """,
                (
                    ref,
                    version,
                    1 if activate else 0,
                    metrics_json,
                    artifact_dir,
                    created_at,
                ),
            )
        except Exception:
            remove_tree_if_present(self.data_dir, artifact_dir)
            raise
        return artifact_dir

    def update_metrics(self, ref: str, metrics: Any) -> ModelRow | None:
        with self._locked() as conn:
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE models
                    SET metrics_json = ?
                    WHERE ref = ? AND deleted = 0
                    """,
                    (json.dumps(metrics), ref),
                )
                if cursor.rowcount == 0:
                    return None
        return self.get_model(ref)

    def purge_trained_model(
        self, ref: str
    ) -> Literal["ok", "not_found", "not_deletable"]:
        """Tombstone a trained model under the same lock as activate.

        Artifact removal stays inside the lock so a concurrent activate cannot
        keep an active row after the files are gone.
        """

        with self._locked() as conn:
            row = conn.execute(
                f"{_MODEL_SELECT} WHERE ref = ? AND deleted = 0",
                (ref,),
            ).fetchone()
            if row is None:
                return "not_found"
            if bool(row["builtin"]) or bool(row["active"]):
                return "not_deletable"
            artifact_dir = row["artifact_dir"]
            if artifact_dir:
                remove_tree_if_present(self.data_dir, artifact_dir)
            with conn:
                cursor = conn.execute(
                    """
                    UPDATE models
                    SET deleted = 1, active = 0
                    WHERE ref = ? AND deleted = 0 AND builtin = 0 AND active = 0
                    """,
                    (ref,),
                )
                if cursor.rowcount == 0:
                    return "not_deletable"
        return "ok"

    def unpublish_builtin(self) -> None:
        """Drop version 0 when unused; otherwise deactivate it."""

        with self._locked() as conn:
            try:
                with conn:
                    conn.execute("DELETE FROM models WHERE version = 0 AND builtin = 1")
            except sqlite3.IntegrityError:
                with conn:
                    conn.execute(
                        """
                        UPDATE models
                        SET active = 0
                        WHERE version = 0 AND builtin = 1
                        """
                    )

    def insert_model(
        self,
        *,
        ref: str,
        version: int,
        builtin: bool,
        created_at: str,
        artifact_dir: str | None = None,
    ) -> ModelRow:
        """Insert a model version. Does not change the active selection."""

        with self._locked() as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO models (
                        ref, version, builtin, active,
                        metrics_json, artifact_dir, created_at, deleted
                    )
                    VALUES (?, ?, ?, 0, NULL, ?, ?, 0)
                    """,
                    (ref, version, 1 if builtin else 0, artifact_dir, created_at),
                )
        created = self.get_model(ref)
        if created is None:
            raise RuntimeError("failed to persist model version")
        return created

    def insert_inferences(
        self, *, model_ref: str, items: list[InferenceNew]
    ) -> list[InferenceRow]:
        if not items:
            return []
        with self._locked() as conn:
            with conn:
                model_row = conn.execute(
                    "SELECT id FROM models WHERE ref = ? AND deleted = 0",
                    (model_ref,),
                ).fetchone()
                if model_row is None:
                    raise ModelNotFoundError
                model_id = int(model_row["id"])
                image_refs = [item.image_ref for item in items]
                id_by_ref = _image_ids_by_refs(conn, list(dict.fromkeys(image_refs)))
                if len(id_by_ref) != len(set(image_refs)):
                    raise ImageNotFoundError
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO inferences (
                            ref, image_id, model_id, top_class_id, top_confidence,
                            other_mass, low_confidence, scores_json, duration_ms,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.ref,
                            id_by_ref[item.image_ref],
                            model_id,
                            item.top_class_id,
                            item.top_confidence,
                            item.other_mass,
                            1 if item.low_confidence else 0,
                            json.dumps(item.scores),
                            item.duration_ms,
                            item.created_at,
                        ),
                    )
                refs = [item.ref for item in items]
                placeholders = ",".join("?" * len(refs))
                rows = conn.execute(
                    f"{_INFERENCE_SELECT} WHERE inf.ref IN ({placeholders})",
                    refs,
                ).fetchall()
        decoded = [_inference_row(row) for row in rows]
        by_ref = {row.ref: row for row in decoded}
        missing = [ref for ref in refs if ref not in by_ref]
        if missing:
            raise RuntimeError(f"failed to persist inferences: {missing}")
        return [by_ref[ref] for ref in refs]

    def list_inferences_page(
        self, *, limit: int, offset: int
    ) -> tuple[list[InferenceRow], int]:
        with self._locked() as conn:
            total = int(
                conn.execute("SELECT COUNT(*) AS n FROM inferences").fetchone()["n"]
            )
            rows = conn.execute(
                f"{_INFERENCE_SELECT} ORDER BY inf.created_at DESC, inf.ref DESC "
                "LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_inference_row(row) for row in rows], total

    def list_inferences(self) -> list[InferenceRow]:
        with self._locked() as conn:
            rows = conn.execute(
                f"{_INFERENCE_SELECT} ORDER BY inf.created_at ASC, inf.ref ASC"
            ).fetchall()
        return [_inference_row(row) for row in rows]

    def get_images_by_refs(self, refs: list[str]) -> list[ImageRow]:
        unique = list(dict.fromkeys(refs))
        if not unique:
            return []
        found: dict[str, ImageRow] = {}
        with self._locked() as conn:
            for start in range(0, len(unique), IN_QUERY_CHUNK):
                chunk = unique[start : start + IN_QUERY_CHUNK]
                placeholders = ",".join("?" * len(chunk))
                rows = conn.execute(
                    f"{_IMAGE_SELECT} WHERE i.ref IN ({placeholders})",
                    chunk,
                ).fetchall()
                for row in rows:
                    decoded = _image_row(row)
                    found[decoded.ref] = decoded
        missing = [ref for ref in unique if ref not in found]
        if missing:
            raise ImageNotFoundError
        return [found[ref] for ref in unique]

    def list_suggestions_page(
        self,
        *,
        min_confidence: float | None,
        max_confidence: float | None,
        order: str,
        limit: int,
        offset: int,
    ) -> tuple[list[SuggestionRow], int]:
        conditions: list[str] = []
        params: list[object] = []
        if min_confidence is not None:
            conditions.append("s.confidence >= ?")
            params.append(min_confidence)
        if max_confidence is not None:
            conditions.append("s.confidence <= ?")
            params.append(max_confidence)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        direction = "ASC" if order == "asc" else "DESC"
        count_sql = (
            "SELECT COUNT(*) AS n FROM suggestions AS s "
            f"JOIN images AS i ON i.id = s.image_id {where}"
        )
        page_sql = (
            f"{_SUGGESTION_SELECT} {where} "
            f"ORDER BY s.confidence {direction}, i.ref ASC LIMIT ? OFFSET ?"
        )
        with self._locked() as conn:
            total = int(conn.execute(count_sql, params).fetchone()["n"])
            rows = conn.execute(page_sql, [*params, limit, offset]).fetchall()
        return [_suggestion_row(row) for row in rows], total

    def upsert_suggestions(
        self, *, model_ref: str, items: list[SuggestionNew]
    ) -> tuple[int, int]:
        """Return (generated_count, skipped_labeled_count).

        Images that gained a confirmed label after targeting are skipped
        and counted so callers can still satisfy REQ-F-SUG-003.
        """

        if not items:
            return 0, 0
        with self._locked() as conn:
            with conn:
                model_row = conn.execute(
                    "SELECT id FROM models WHERE ref = ?",
                    (model_ref,),
                ).fetchone()
                if model_row is None:
                    raise ModelNotFoundError
                model_id = int(model_row["id"])
                refs = list(dict.fromkeys(item.image_ref for item in items))
                id_by_ref = _image_ids_by_refs(conn, refs)
                if len(id_by_ref) != len(refs):
                    raise ImageNotFoundError
                generated = 0
                skipped_labeled = 0
                for item in items:
                    image_id = id_by_ref[item.image_ref]
                    labeled = conn.execute(
                        "SELECT 1 FROM labels WHERE image_id = ?",
                        (image_id,),
                    ).fetchone()
                    if labeled is not None:
                        skipped_labeled += 1
                        continue
                    conn.execute(
                        """
                        INSERT INTO suggestions (
                            image_id, class_id, confidence, model_id, created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(image_id) DO UPDATE SET
                            class_id = excluded.class_id,
                            confidence = excluded.confidence,
                            model_id = excluded.model_id,
                            created_at = excluded.created_at
                        """,
                        (
                            image_id,
                            item.class_id,
                            item.confidence,
                            model_id,
                            item.created_at,
                        ),
                    )
                    generated += 1
        return generated, skipped_labeled

    def accept_suggestions(self, refs: list[str], assigned_at: str) -> int:
        unique = list(dict.fromkeys(refs))
        with self._locked() as conn:
            with conn:
                id_by_ref = _image_ids_by_refs(conn, unique)
                if len(id_by_ref) != len(unique):
                    raise ImageNotFoundError
                accepted = 0
                for ref in unique:
                    suggestion = conn.execute(
                        """
                        SELECT class_id
                        FROM suggestions
                        WHERE image_id = ?
                        """,
                        (id_by_ref[ref],),
                    ).fetchone()
                    if suggestion is None:
                        continue
                    _upsert_label_row(
                        conn,
                        id_by_ref[ref],
                        str(suggestion["class_id"]),
                        "model_suggested",
                        assigned_at,
                    )
                    accepted += 1
        return accepted

    def accept_suggestions_by_threshold(
        self, min_confidence: float, assigned_at: str
    ) -> int:
        with self._locked() as conn:
            with conn:
                rows = conn.execute(
                    """
                    SELECT i.id AS image_id, s.class_id AS class_id
                    FROM suggestions AS s
                    JOIN images AS i ON i.id = s.image_id
                    LEFT JOIN labels AS l ON l.image_id = i.id
                    WHERE s.confidence >= ?
                      AND l.image_id IS NULL
                    ORDER BY i.ref ASC
                    """,
                    (min_confidence,),
                ).fetchall()
                for row in rows:
                    _upsert_label_row(
                        conn,
                        int(row["image_id"]),
                        str(row["class_id"]),
                        "model_suggested",
                        assigned_at,
                    )
        return len(rows)

    def delete_suggestions(self, refs: list[str]) -> int:
        unique = list(dict.fromkeys(refs))
        with self._locked() as conn:
            with conn:
                id_by_ref = _image_ids_by_refs(conn, unique)
                if len(id_by_ref) != len(unique):
                    raise SuggestionNotFoundError
                for ref in unique:
                    deleted = conn.execute(
                        "DELETE FROM suggestions WHERE image_id = ?",
                        (id_by_ref[ref],),
                    )
                    if deleted.rowcount != 1:
                        raise SuggestionNotFoundError
        return len(unique)


_INFERENCE_SELECT = """
SELECT
    inf.ref AS ref,
    img.ref AS image_ref,
    m.ref AS model_ref,
    inf.top_class_id AS top_class_id,
    inf.top_confidence AS top_confidence,
    inf.other_mass AS other_mass,
    inf.low_confidence AS low_confidence,
    inf.scores_json AS scores_json,
    inf.created_at AS created_at
FROM inferences AS inf
JOIN images AS img ON img.id = inf.image_id
JOIN models AS m ON m.id = inf.model_id
"""

_JOB_SELECT = """
SELECT
    j.ref AS ref,
    j.status AS status,
    j.current_epoch AS current_epoch,
    j.total_epochs AS total_epochs,
    m.ref AS model_ref,
    j.created_at AS created_at,
    j.params_json AS params_json,
    j.failed_reason AS failed_reason
FROM jobs AS j
LEFT JOIN models AS m ON m.id = j.model_id
"""


def _utc_now_z() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job_row(row: sqlite3.Row) -> JobRow:
    return JobRow(
        ref=row["ref"],
        status=row["status"],
        current_epoch=int(row["current_epoch"]),
        total_epochs=int(row["total_epochs"]),
        model_ref=row["model_ref"],
        created_at=row["created_at"],
        params=_decode_json(row["params_json"]),
        failed_reason=row["failed_reason"],
    )


def _suggestion_row(row: sqlite3.Row) -> SuggestionRow:
    return SuggestionRow(
        image_ref=row["image_ref"],
        class_id=row["class_id"],
        confidence=float(row["confidence"]),
        model_ref=row["model_ref"],
    )


_SUGGESTION_SELECT = """
SELECT
    i.ref AS image_ref,
    s.class_id AS class_id,
    s.confidence AS confidence,
    m.ref AS model_ref
FROM suggestions AS s
JOIN images AS i ON i.id = s.image_id
JOIN models AS m ON m.id = s.model_id
"""


def _inference_row(row: sqlite3.Row) -> InferenceRow:
    return InferenceRow(
        ref=row["ref"],
        image_ref=row["image_ref"],
        model_ref=row["model_ref"],
        top_class_id=row["top_class_id"],
        top_confidence=float(row["top_confidence"]),
        other_mass=(None if row["other_mass"] is None else float(row["other_mass"])),
        low_confidence=bool(row["low_confidence"]),
        scores=_decode_json(row["scores_json"]),
        created_at=row["created_at"],
    )


def _model_row(row: sqlite3.Row) -> ModelRow:
    return ModelRow(
        ref=row["ref"],
        version=int(row["version"]),
        builtin=bool(row["builtin"]),
        active=bool(row["active"]),
        metrics=_decode_json(row["metrics_json"]),
        created_at=row["created_at"],
        artifact_dir=row["artifact_dir"],
    )


def _image_row(row: sqlite3.Row) -> ImageRow:
    return ImageRow(
        ref=row["ref"],
        sha256=row["sha256"],
        split=row["split"],
        label_class_id=row["label_class_id"],
        label_source=row["label_source"],
        suggestion_class_id=row["suggestion_class_id"],
        suggestion_confidence=(
            None
            if row["suggestion_confidence"] is None
            else float(row["suggestion_confidence"])
        ),
        suggestion_model_ref=row["suggestion_model_ref"],
        created_at=row["created_at"],
        original_name=row["original_name"],
        size_bytes=int(row["size_bytes"]),
        width=None if row["width"] is None else int(row["width"]),
        height=None if row["height"] is None else int(row["height"]),
        path=row["path"],
    )


def _decode_json(raw: str | None) -> Any:
    if raw is None:
        return None
    return json.loads(raw)


def _upsert_label_row(
    conn: sqlite3.Connection,
    image_id: int,
    class_id: str,
    source: str,
    assigned_at: str,
) -> None:
    conn.execute("DELETE FROM suggestions WHERE image_id = ?", (image_id,))
    conn.execute(
        """
        INSERT INTO labels (image_id, class_id, source, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(image_id) DO UPDATE SET
            class_id = excluded.class_id,
            source = excluded.source,
            created_at = excluded.created_at
        """,
        (image_id, class_id, source, assigned_at),
    )


def _image_ids_by_refs(conn: sqlite3.Connection, refs: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for start in range(0, len(refs), IN_QUERY_CHUNK):
        chunk = refs[start : start + IN_QUERY_CHUNK]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT id, ref FROM images WHERE ref IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            found[str(row["ref"])] = int(row["id"])
    return found


def _apply_split_assignments(
    conn: sqlite3.Connection, assignments: dict[str, str]
) -> tuple[int, int]:
    conn.execute("UPDATE images SET split = 'unassigned'")
    if assignments:
        conn.executemany(
            "UPDATE images SET split = ? WHERE ref = ?",
            [(split, ref) for ref, split in assignments.items()],
        )
    assigned = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM images WHERE split != 'unassigned'"
        ).fetchone()["n"]
    )
    unassigned = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM images WHERE split = 'unassigned'"
        ).fetchone()["n"]
    )
    return assigned, unassigned
