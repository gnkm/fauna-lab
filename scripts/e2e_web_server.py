#!/usr/bin/env python3
"""Start FastAPI with an empty data dir and built web/dist for Playwright."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "web" / "dist"


def main() -> int:
    if not (DIST / "index.html").is_file():
        print(
            "web/dist/index.html がありません。先に pnpm --filter web build を実行してください。",
            file=sys.stderr,
        )
        return 1
    data = Path(tempfile.mkdtemp(prefix="faunalab-e2e-"))
    env = os.environ.copy()
    env["FAUNALAB_DATA_DIR"] = str(data / "data")
    env["FAUNALAB_ASSETS_DIR"] = str(data / "missing-assets")
    env["FAUNALAB_WEB_DIST_DIR"] = str(DIST)
    port = env.get("FAUNALAB_E2E_PORT", "4173")
    cmd = [
        "uv",
        "run",
        "--directory",
        str(ROOT / "backend"),
        "uvicorn",
        "faunalab.api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        port,
    ]
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
