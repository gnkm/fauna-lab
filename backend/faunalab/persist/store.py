"""SQLite store under FAUNALAB_DATA_DIR (REQ-DATA-011, REQ-F-SYS-002)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from faunalab.domain.classes import SYSTEM_CLASSES
from faunalab.persist.schema import SCHEMA_SQL, SCHEMA_VERSION

LOGGER = logging.getLogger("faunalab.persist")

DATA_SUBDIRS: tuple[str, ...] = ("images", "thumbs", "models", "jobs")
DB_FILENAME = "db.sqlite3"

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


@dataclass(frozen=True, slots=True)
class ModelRow:
    ref: str
    version: int
    builtin: bool
    active: bool
    metrics: Any
    created_at: str


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
                self._recover_interrupted_jobs(conn)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

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
        conn.execute(
            """
            UPDATE jobs
            SET status = 'FAILED',
                failed_reason = 'プロセス中断',
                finished_at = datetime('now')
            WHERE status = 'RUNNING'
            """
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
                    j.created_at AS created_at
                FROM jobs AS j
                LEFT JOIN models AS m ON m.id = j.model_id
                ORDER BY j.created_at ASC, j.ref ASC
                """
            ).fetchall()
        return [
            JobRow(
                ref=row["ref"],
                status=row["status"],
                current_epoch=int(row["current_epoch"]),
                total_epochs=int(row["total_epochs"]),
                model_ref=row["model_ref"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_models(self) -> list[ModelRow]:
        with self._locked() as conn:
            rows = conn.execute(
                """
                SELECT ref, version, builtin, active, metrics_json, created_at
                FROM models
                ORDER BY version ASC
                """
            ).fetchall()
        return [
            ModelRow(
                ref=row["ref"],
                version=int(row["version"]),
                builtin=bool(row["builtin"]),
                active=bool(row["active"]),
                metrics=_decode_json(row["metrics_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_inferences(self) -> list[InferenceRow]:
        with self._locked() as conn:
            rows = conn.execute(
                """
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
                ORDER BY inf.created_at ASC, inf.ref ASC
                """
            ).fetchall()
        return [
            InferenceRow(
                ref=row["ref"],
                image_ref=row["image_ref"],
                model_ref=row["model_ref"],
                top_class_id=row["top_class_id"],
                top_confidence=float(row["top_confidence"]),
                other_mass=(
                    None if row["other_mass"] is None else float(row["other_mass"])
                ),
                low_confidence=bool(row["low_confidence"]),
                scores=_decode_json(row["scores_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]


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
