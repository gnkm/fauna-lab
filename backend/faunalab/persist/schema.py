"""SQLite DDL for the persistence vessel (DESIGN.md 6)."""

from __future__ import annotations

SCHEMA_VERSION = 2

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS classes (
    class_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    display_order INTEGER NOT NULL UNIQUE
        CHECK (display_order BETWEEN 1 AND 8),
    CHECK (
        class_id IN (
            'samoyed',
            'great_pyrenees',
            'boxer',
            'american_bulldog',
            'chihuahua',
            'miniature_pinscher',
            'pomeranian',
            'havanese'
        )
    )
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    width INTEGER,
    height INTEGER,
    split TEXT NOT NULL DEFAULT 'unassigned'
        CHECK (split IN ('train', 'val', 'test', 'unassigned')),
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS images_created_at_ref
    ON images (created_at, ref);

CREATE TABLE IF NOT EXISTS labels (
    image_id INTEGER PRIMARY KEY
        REFERENCES images(id) ON DELETE CASCADE,
    class_id TEXT NOT NULL REFERENCES classes(class_id),
    source TEXT NOT NULL CHECK (source IN ('human', 'model_suggested')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL UNIQUE,
    builtin INTEGER NOT NULL CHECK (builtin IN (0, 1)),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    metrics_json TEXT,
    artifact_dir TEXT,
    created_at TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
    CHECK (
        (builtin = 1 AND version = 0)
        OR (builtin = 0 AND version <> 0)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS models_one_active
    ON models (active) WHERE active = 1;

CREATE TABLE IF NOT EXISTS suggestions (
    image_id INTEGER PRIMARY KEY
        REFERENCES images(id) ON DELETE CASCADE,
    class_id TEXT NOT NULL REFERENCES classes(class_id),
    confidence REAL NOT NULL,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL
        CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED')),
    current_epoch INTEGER NOT NULL DEFAULT 0,
    total_epochs INTEGER NOT NULL,
    model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
    params_json TEXT,
    failed_reason TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS jobs_created_at_ref
    ON jobs (created_at, ref);

CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_running
    ON jobs (status) WHERE status = 'RUNNING';

CREATE TABLE IF NOT EXISTS inferences (
    id INTEGER PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    top_class_id TEXT NOT NULL REFERENCES classes(class_id),
    top_confidence REAL NOT NULL,
    other_mass REAL,
    low_confidence INTEGER NOT NULL CHECK (low_confidence IN (0, 1)),
    scores_json TEXT NOT NULL,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS inferences_created_at_ref
    ON inferences (created_at, ref);
"""
