"""Matrix completeness: every SRS VER ID is listed and automated rows are reachable."""

from __future__ import annotations

from tests.ver_catalog import (
    MATRIX_PATH,
    REPO_ROOT,
    VER_RE,
    load_matrix,
    marker_slug,
    parse_test_refs,
    python_function_names,
    ref_covers_ver_id,
    resolve_matrix_test_path,
    srs_ver_ids,
)

SEARCH_SUFFIXES = {".py", ".ts", ".md"}
SKIP_PARTS = {".venv", "node_modules", ".git", "assets"}
# 対応表と DESIGN の再掲だけでは、試験が存在する扱いにしない。
SKIP_NAMES = {MATRIX_PATH.name, "DESIGN.md"}


def test_verification_matrix_lists_every_srs_ver_id() -> None:
    """対応表に SRS 4 章の VER ID が漏れなく載る。"""

    listed = [row.ver_id for row in load_matrix()]
    assert listed, f"no rows in {MATRIX_PATH}"
    assert len(listed) == len(set(listed))
    from_srs = srs_ver_ids()
    assert from_srs
    missing = from_srs - set(listed)
    extra = set(listed) - from_srs
    assert missing == set(), f"SRS VER IDs missing from matrix: {sorted(missing)}"
    assert extra == set(), f"matrix VER IDs not in SRS: {sorted(extra)}"


def test_automated_ver_ids_are_mentioned_in_tests() -> None:
    """pytest / inspect / playwright 行の試験列は実ファイルと関数を指す。"""

    for row in load_matrix():
        automated = any(
            token in row.method for token in ("pytest", "inspect", "playwright")
        )
        if not automated:
            continue
        refs = parse_test_refs(row.tests)
        assert refs, f"{row.ver_id}: 試験列にファイルが無い: {row.tests!r}"
        covered = False
        for spec, func in refs:
            path = resolve_matrix_test_path(spec)
            assert path.is_file(), f"{row.ver_id}: missing {path}"
            if func is not None and path.suffix == ".py":
                names = python_function_names(path)
                assert func in names, f"{row.ver_id}: {path.name} has no {func}"
            if ref_covers_ver_id(path, func, row.ver_id):
                covered = True
        assert covered, f"{row.ver_id}: 試験列のファイルに VER ID が無い"
        slug = marker_slug(row.ver_id)
        assert slug.startswith("ver_")


def test_issue_verification_finds_ver_mapping() -> None:
    """Issue 検証欄と同等: リポジトリ内に VER- 対応がある。"""

    hits = 0
    for path in REPO_ROOT.rglob("*"):
        if path.suffix not in SEARCH_SUFFIXES or not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.name in SKIP_NAMES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "VER-" in text:
            hits += 1
    assert hits >= 1
    assert VER_RE.search(MATRIX_PATH.read_text(encoding="utf-8"))
