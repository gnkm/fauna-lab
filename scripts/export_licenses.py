#!/usr/bin/env python3
"""Export installed dependency licenses for VER-CON-002 (no network)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export_python(dest: Path) -> None:
    cmd = [
        "uv",
        "run",
        "--directory",
        str(ROOT / "backend"),
        "pip-licenses",
        "--format=markdown",
        f"--output-file={dest}",
        "--ignore-packages=faunalab",
    ]
    subprocess.run(cmd, check=True)


def _license_of(pkg: dict[str, object]) -> str:
    raw = pkg.get("license")
    if isinstance(raw, str) and raw.strip():
        return raw
    licenses = pkg.get("licenses")
    if isinstance(licenses, list):
        parts: list[str] = []
        for item in licenses:
            if isinstance(item, dict):
                parts.append(str(item.get("type") or item.get("name") or item))
            else:
                parts.append(str(item))
        if parts:
            return "; ".join(parts)
    return "UNKNOWN"


def _web_package_jsons(store: Path) -> list[Path]:
    # unscoped:  .pnpm/foo@1/node_modules/foo/package.json
    # scoped:    .pnpm/@scope+bar@1/node_modules/@scope/bar/package.json
    found = {
        *store.glob("*/node_modules/*/package.json"),
        *store.glob("*/node_modules/@*/*/package.json"),
    }
    return sorted(found)


def iter_web_packages(root: Path | None = None) -> list[tuple[str, str, str]]:
    store = (root or ROOT) / "node_modules" / ".pnpm"
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    if not store.is_dir():
        return rows
    for pkg_json in _web_package_jsons(store):
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        name = str(data.get("name") or pkg_json.parent.name)
        version = str(data.get("version") or "")
        key = (name, version)
        if key in seen:
            continue
        seen.add(key)
        rows.append((name, version, _license_of(data)))
    rows.sort()
    return rows


def export_web(dest: Path) -> None:
    rows = iter_web_packages()
    lines = [
        "# Frontend dependency licenses",
        "",
        "Generated from `node_modules/.pnpm` package metadata. No network.",
        "",
        "| Name | Version | License |",
        "| --- | --- | --- |",
    ]
    for name, version, license_name in rows:
        lines.append(f"| {name} | {version} | {license_name} |")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python-out",
        type=Path,
        default=ROOT / "docs/dependency-licenses-python.md",
    )
    parser.add_argument(
        "--web-out",
        type=Path,
        default=ROOT / "docs/dependency-licenses-web.txt",
    )
    args = parser.parse_args()
    args.python_out.parent.mkdir(parents=True, exist_ok=True)
    export_python(args.python_out)
    export_web(args.web_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
