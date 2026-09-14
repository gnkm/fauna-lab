"""Parse `docs/verification-matrix.md` and collect VER IDs from tests."""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "docs" / "verification-matrix.md"
SRS_PATH = REPO_ROOT / "docs" / "source-of-truth" / "srs-faunalab.md"

VER_RE = re.compile(r"VER-[A-Z]+(?:-[A-Z]+)*-\d{3}")
ROW_RE = re.compile(
    r"^\| `(VER-[A-Z]+(?:-[A-Z]+)*-\d{3})` \| ([^|]+) \| ([^|]+) \|"
)
TEST_NAME_RE = re.compile(r"^test_ver_([a-z0-9_]+)_(\d{3})(?:_|$)")
# 試験列から pytest / Playwright の参照を拾う。対応表自身は対象外。
TEST_REF_RE = re.compile(r"(e2e/[\w./-]+\.ts|[\w.-]+\.py)(?:::([A-Za-z_][\w]*))?")
PY_DEF_RE = re.compile(r"^def ([A-Za-z_][\w]*)\(", re.MULTILINE)


class MatrixRow(NamedTuple):
    ver_id: str
    method: str
    tests: str
    notes: str


def marker_slug(ver_id: str) -> str:
    return ver_id.lower().replace("-", "_")


def ver_id_from_test_name(name: str) -> str | None:
    match = TEST_NAME_RE.match(name)
    if match is None:
        return None
    prefix = match.group(1).upper().replace("_", "-")
    return f"VER-{prefix}-{match.group(2)}"


def load_matrix() -> list[MatrixRow]:
    rows: list[MatrixRow] = []
    for line in MATRIX_PATH.read_text(encoding="utf-8").splitlines():
        match = ROW_RE.match(line)
        if match is None:
            continue
        rows.append(
            MatrixRow(
                ver_id=match.group(1),
                method=match.group(2).strip(),
                tests=match.group(3).strip(),
                notes="",
            )
        )
    return rows


def srs_ver_ids() -> set[str]:
    return set(VER_RE.findall(SRS_PATH.read_text(encoding="utf-8")))


def ver_ids_in_text(text: str) -> set[str]:
    return set(VER_RE.findall(text))


def parse_test_refs(tests: str) -> list[tuple[str, str | None]]:
    """試験列から (ファイル, 任意の関数名) を取り出す。"""

    return [(match.group(1), match.group(2)) for match in TEST_REF_RE.finditer(tests)]


def resolve_matrix_test_path(spec: str) -> Path:
    if spec.startswith("e2e/"):
        return REPO_ROOT / spec
    return REPO_ROOT / "backend" / "tests" / Path(spec).name


def python_function_names(path: Path) -> set[str]:
    return set(PY_DEF_RE.findall(path.read_text(encoding="utf-8")))


def ref_covers_ver_id(path: Path, func: str | None, ver_id: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if ver_id in text:
        return True
    if func is not None and ver_id_from_test_name(func) == ver_id:
        return True
    return False
