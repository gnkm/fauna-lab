"""Spawn the training worker in a separate interpreter (no PyTorch in API)."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

LOGGER = logging.getLogger("faunalab.jobs")


def start_worker(data_dir: Path, assets_dir: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "faunalab.jobs.worker",
            str(data_dir),
            str(assets_dir),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
    )


def stop_worker(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        LOGGER.warning("training worker did not stop; killing")
        proc.kill()
        proc.wait(timeout=5)
