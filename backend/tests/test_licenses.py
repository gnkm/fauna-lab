"""Installed Python dependency licenses (REQ-CON-003)."""

from __future__ import annotations

import importlib.metadata
import re

# ARCHITECTURE.md 4.1 の OSI 承認かつ copyleft を避ける集合。
ALLOWED_SPDX = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BlueOak-1.0.0",
        "HPND",
        "ISC",
        "MIT",
        "MIT-0",
        "MIT-CMU",
        "MPL-2.0",
        "PSF-2.0",
        "Python-2.0",
        "Unlicense",
        "Zlib",
    }
)

LICENSE_ALIASES = {
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "isc license": "ISC",
    "mit": "MIT",
    "mit license": "MIT",
    "mit-cmu": "MIT-CMU",
    "mozilla public license 2.0": "MPL-2.0",
    "python software foundation license": "PSF-2.0",
    "the unlicense": "Unlicense",
    "3-clause bsd license": "BSD-3-Clause",
}

DENIED_SUBSTRINGS = ("gpl", "agpl", "sspl", "commons clause")


def _normalize_token(raw: str) -> str:
    compact = re.sub(r"\s+", " ", raw.strip())
    return LICENSE_ALIASES.get(compact.lower(), compact)


def _split_license_expression(raw: str) -> list[str]:
    parts = re.split(r"\s+(?:AND|OR)\s+|[;,]", raw, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def _classifiers_to_spdx(classifiers: list[str]) -> list[str]:
    found: list[str] = []
    for item in classifiers:
        if not item.startswith("License ::"):
            continue
        tail = item.rsplit("::", 1)[-1].strip()
        if tail.lower() in {"osi approved", "osi approved ::"}:
            continue
        found.append(_normalize_token(tail))
    return found


def test_runtime_and_dev_packages_are_permissive() -> None:
    violations: list[str] = []
    unknown: list[str] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name.lower() == "faunalab":
            continue
        raw = (
            dist.metadata.get("License-Expression")
            or dist.metadata.get("License")
            or ""
        )
        classifiers = dist.metadata.get_all("Classifier") or []
        tokens = [_normalize_token(part) for part in _split_license_expression(raw)]
        tokens.extend(_classifiers_to_spdx(classifiers))
        lowered = " ".join(tokens).lower()
        if any(denied in lowered for denied in DENIED_SUBSTRINGS):
            violations.append(f"{name}: {raw or classifiers}")
            continue
        spdx_tokens = [token for token in tokens if token in ALLOWED_SPDX]
        if not spdx_tokens:
            unknown.append(f"{name}: license={raw!r} classifiers={classifiers}")
    assert not violations, f"copyleft or non-permissive: {violations}"
    assert not unknown, f"unmapped license metadata: {unknown}"
