"""Reuse ONNX Runtime sessions across inference and suggestion requests."""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Protocol

from faunalab.ml.predict import load_onnx_session

# One active model at a time (REQ-F-MDL-003). Keep only the latest trained session.
_MAX_TRAINED_SESSIONS = 1


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
    """Keep the latest trained session; reload on mtime or size change."""

    def __init__(self, max_sessions: int = _MAX_TRAINED_SESSIONS) -> None:
        self._max_sessions = max_sessions
        self._guard = threading.Lock()
        self._items: OrderedDict[str, tuple[tuple[int, int], LockedOnnxSession]] = (
            OrderedDict()
        )

    def get(self, path: Path) -> LockedOnnxSession:
        resolved = str(path.resolve())
        stat = path.stat()
        fingerprint = (stat.st_mtime_ns, stat.st_size)
        with self._guard:
            current = self._items.get(resolved)
            if current is not None and current[0] == fingerprint:
                self._items.move_to_end(resolved)
                return current[1]
            wrapped = LockedOnnxSession(load_onnx_session(path))
            self._items[resolved] = (fingerprint, wrapped)
            self._items.move_to_end(resolved)
            while len(self._items) > self._max_sessions:
                self._items.popitem(last=False)
            return wrapped
