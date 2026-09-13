"""Spawn and keep the training worker in a separate interpreter."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

LOGGER = logging.getLogger("faunalab.jobs")


class WorkerSupervisor:
    """One training worker. Restart it if the child exits unexpectedly."""

    def __init__(
        self,
        data_dir: Path,
        assets_dir: Path,
        *,
        argv: list[str] | None = None,
        poll_seconds: float = 0.5,
    ) -> None:
        self._data_dir = data_dir
        self._assets_dir = assets_dir
        self._argv = argv
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None
        self._proc = self._spawn()
        self._thread = threading.Thread(
            target=self._loop,
            name="faunalab-worker-watch",
            daemon=True,
        )
        self._thread.start()

    def _spawn(self) -> subprocess.Popen[bytes]:
        command = self._argv or [
            sys.executable,
            "-m",
            "faunalab.jobs.worker",
            str(self._data_dir),
            str(self._assets_dir),
        ]
        return subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[2]),
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                if not self._stop.is_set():
                    LOGGER.warning(
                        "training worker exited with %s; restarting",
                        proc.returncode,
                    )
                    self._proc = self._spawn()
            self._stop.wait(self._poll_seconds)
        self._terminate()

    def _terminate(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            LOGGER.warning("training worker did not stop; killing")
            proc.kill()
            proc.wait(timeout=5)

    def stop(self) -> None:
        self._stop.set()
        self._terminate()
        self._thread.join(timeout=8)


def start_worker(
    data_dir: Path,
    assets_dir: Path,
    *,
    argv: list[str] | None = None,
    poll_seconds: float = 0.5,
) -> WorkerSupervisor:
    return WorkerSupervisor(data_dir, assets_dir, argv=argv, poll_seconds=poll_seconds)


def stop_worker(proc: WorkerSupervisor | None) -> None:
    if proc is None:
        return
    proc.stop()
