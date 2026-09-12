"""Frontend lockfile licenses (REQ-CON-003)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Python 側の OSI 集合。CC-BY-4.0 は全パッケージ許可にしない。
ALLOWED_WEB_SPDX = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BlueOak-1.0.0",
        "HPND",
        "ISC",
        "MIT",
        "MIT-0",
        "MPL-2.0",
        "PSF-2.0",
        "Unlicense",
        "Zlib",
    }
)

# ARCHITECTURE.md 4.1.6。名前で列挙したデータパッケージだけ CC-BY-4.0 を許す。
DATA_PACKAGES_CC_BY_4_0 = frozenset({"caniuse-lite"})

LICENSE_ALIASES = {
    "apache-2.0": "Apache-2.0",
    "bsd-3-clause": "BSD-3-Clause",
    "cc-by-4.0": "CC-BY-4.0",
    "isc": "ISC",
    "mit": "MIT",
}

REQUIRED_SCOPED = (
    "@vitejs/plugin-react",
    "@types/react",
    "@biomejs/biome",
)


def _load_exporter():
    path = ROOT / "scripts" / "export_licenses.py"
    spec = importlib.util.spec_from_file_location("export_licenses", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize(raw: str) -> str:
    return LICENSE_ALIASES.get(raw.strip().lower(), raw.strip())


def _tokens(raw: str) -> list[str]:
    parts = re.split(r"\s+(?:AND|OR)\s+", raw, flags=re.IGNORECASE)
    return [_normalize(part) for part in parts if part.strip()]


def test_pnpm_store_includes_scoped_packages() -> None:
    exporter = _load_exporter()
    names = {name for name, _version, _license in exporter.iter_web_packages(ROOT)}
    missing = [item for item in REQUIRED_SCOPED if item not in names]
    assert not missing, f"scoped packages missing from pnpm store scan: {missing}"


def test_committed_web_license_list_includes_scoped_packages() -> None:
    text = (ROOT / "docs" / "dependency-licenses-web.txt").read_text(encoding="utf-8")
    missing = [item for item in REQUIRED_SCOPED if f"| {item} |" not in text]
    assert not missing, f"scoped packages missing from committed list: {missing}"


def test_committed_web_licenses_are_permissive() -> None:
    unknown: list[str] = []
    for line in (
        (ROOT / "docs" / "dependency-licenses-web.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        if not line.startswith("| ") or line.startswith("| Name"):
            continue
        if set(line.replace("|", "").replace("-", "").split()) == set():
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) != 3 or parts[0] == "---":
            continue
        name, _version, license_name = parts
        tokens = _tokens(license_name)
        allowed = ALLOWED_WEB_SPDX
        if name in DATA_PACKAGES_CC_BY_4_0:
            allowed = ALLOWED_WEB_SPDX | {"CC-BY-4.0"}
        if not tokens or any(token not in allowed for token in tokens):
            unknown.append(f"{name}: {license_name}")
    assert not unknown, f"unmapped or disallowed web licenses: {unknown}"
