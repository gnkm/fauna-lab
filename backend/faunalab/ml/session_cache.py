"""Reuse ONNX Runtime sessions across inference and suggestion requests."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Protocol

from faunalab.ml.predict import load_onnx_session


class OnnxRunnable(Protocol):
    def get_inputs(self) -> Any: ...

    def get_outputs(self) -> Any: ...

    def run(self, *args: Any, **kwargs: Any) -> Any: ...


class LockedOnnxSession:
    """Serialize `run` so a shared session is safe across requests."""

    def __init__(self, session: Any, lock: threading.Lock | None = None) -> None:
        self._session = session
        self._lock = lock or threading.Lock()

    def get_inputs(self) -> Any:
        return self._session.get_inputs()

    def get_outputs(self) -> Any:
        return self._session.get_outputs()

    def run(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._session.run(*args, **kwargs)


class OnnxSessionCache:
    """Keep one session per resolved artifact path; reload on mtime or size change."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._items: dict[str, tuple[tuple[int, int], LockedOnnxSession]] = {}

    def get(self, path: Path) -> LockedOnnxSession:
        resolved = str(path.resolve())
        stat = path.stat()
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        with self._guard:
            current = self._items.get(resolved)
            if current is not None and current[0] == fingerprint:
                return current[1]
            wrapped = LockedOnnxSession(load_onnx_session(path))
            self._items[resolved] = (fingerprint, wrapped)
            return wrapped
