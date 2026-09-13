"""Image management API (F008).

Verification mapping:
- VER-F-IMG-001 (REQ-F-IMG-001〜003): test_ver_f_img_001_jpeg_png_fake_and_oversize
- VER-F-IMG-002 (REQ-F-IMG-005 / REQ-F-IMG-006):
  test_ver_f_img_002_partial_success_and_duplicate
- VER-F-IMG-003 (REQ-SYS-002): test_ver_f_img_003_survives_restart
- VER-F-IMG-004 (REQ-F-IMG-008、REQ-API-006): test_ver_f_img_004_filter_and_pagination
- VER-F-IMG-005 (REQ-F-IMG-009、REQ-DATA-009、REQ-ATT-SEC-001):
  test_ver_f_img_005_delete_cascade_and_path_traversal
"""

from __future__ import annotations

import io
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from faunalab.api.app import create_app
from faunalab.api.errors import PROBLEM_JSON
from faunalab.domain.images import MAX_IMAGE_BYTES, THUMB_LONG_EDGE
from faunalab.persist.store import DB_FILENAME, Store
from faunalab.settings import Settings
from PIL import Image


def _image_bytes(
    fmt: str,
    *,
    size: tuple[int, int] = (32, 24),
    color: tuple[int, int, int] = (10, 20, 30),
) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _jpeg(**kwargs: Any) -> bytes:
    return _image_bytes("JPEG", **kwargs)


def _png(**kwargs: Any) -> bytes:
    return _image_bytes("PNG", **kwargs)


def _oversize_jpeg() -> bytes:
    small = _jpeg(size=(8, 8))
    pad = MAX_IMAGE_BYTES + 1 - len(small)
    return small + (b"\x00" * max(pad, 1))


def _upload(client: TestClient, parts: list[tuple[str, bytes, str]]) -> Any:
    files = [
        ("files", (name, data, content_type)) for name, data, content_type in parts
    ]
    return client.post("/api/images", files=files)


def _state_images(client: TestClient) -> list[dict[str, Any]]:
    return client.get("/api/_state").json()["images"]


def test_ver_f_img_001_jpeg_png_fake_and_oversize(client: TestClient) -> None:
    """VER-F-IMG-001: JPEG/PNG は登録。偽装テキストは 415、10 MiB 超は 413。"""
    jpeg = _jpeg(color=(1, 2, 3))
    png = _png(color=(4, 5, 6))
    fake = b"this is not an image"
    oversize = _oversize_jpeg()
    assert len(oversize) > MAX_IMAGE_BYTES

    ok_jpeg = _upload(client, [("a.jpg", jpeg, "image/jpeg")])
    assert ok_jpeg.status_code == 200
    assert ok_jpeg.json()["items"][0]["ok"] is True

    ok_png = _upload(client, [("b.png", png, "image/png")])
    assert ok_png.status_code == 200
    assert ok_png.json()["items"][0]["ok"] is True

    fake_resp = _upload(client, [("photo.jpg", fake, "image/jpeg")])
    assert fake_resp.status_code == 415
    assert fake_resp.headers["content-type"].startswith(PROBLEM_JSON)
    assert fake_resp.json()["code"] == "unsupported_media_type"

    big_resp = _upload(client, [("huge.jpg", oversize, "image/jpeg")])
    assert big_resp.status_code == 413
    assert big_resp.headers["content-type"].startswith(PROBLEM_JSON)
    assert big_resp.json()["code"] == "payload_too_large"
    assert fake_resp.status_code != big_resp.status_code

    images = _state_images(client)
    assert len(images) == 2
    shas = {item["sha256"] for item in images}
    assert len(shas) == 2


def test_ver_f_img_002_partial_success_and_duplicate(client: TestClient) -> None:
    """VER-F-IMG-002: 有効 2・無効 1・重複 1 を 1 要求で投入する。"""
    first = _jpeg(color=(11, 0, 0))
    second = _png(color=(0, 11, 0))
    registered = _upload(client, [("keep.jpg", first, "image/jpeg")])
    assert registered.status_code == 200
    before = len(_state_images(client))

    response = _upload(
        client,
        [
            ("one.jpg", _jpeg(color=(1, 1, 1)), "image/jpeg"),
            ("two.png", second, "image/png"),
            ("fake.jpg", b"not-an-image", "image/jpeg"),
            ("dup.jpg", first, "image/jpeg"),
        ],
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 4
    assert items[0]["ok"] is True
    assert items[1]["ok"] is True
    assert items[2]["ok"] is False
    assert items[2]["code"] == "unsupported_media_type"
    assert items[3]["ok"] is False
    assert items[3]["code"] == "image_duplicate"
    codes = [item.get("code") for item in items if not item["ok"]]
    assert codes[0] != codes[1]
    assert len(_state_images(client)) == before + 2


def test_ver_f_img_003_survives_restart(settings: Settings) -> None:
    """VER-F-IMG-003: 再起動後も `_state` の画像が一致する。"""
    jpeg = _jpeg(color=(9, 9, 9))
    with TestClient(create_app(settings)) as first:
        uploaded = _upload(first, [("persist.jpg", jpeg, "image/jpeg")])
        assert uploaded.status_code == 200
        before = first.get("/api/_state").json()
    with TestClient(create_app(settings)) as second:
        after = second.get("/api/_state").json()
    before.pop("observed_at")
    after.pop("observed_at")
    assert after["images"] == before["images"]
    assert len(after["images"]) == 1


def test_ver_f_img_004_filter_and_pagination(
    client: TestClient, settings: Settings
) -> None:
    """VER-F-IMG-004: 絞り込み件数と順序の一意性。"""
    colors = [(i, 0, 0) for i in range(1, 5)]
    refs: list[str] = []
    for index, color in enumerate(colors):
        fmt = "JPEG" if index % 2 == 0 else "PNG"
        name = f"img{index}.jpg" if fmt == "JPEG" else f"img{index}.png"
        body = _jpeg(color=color) if fmt == "JPEG" else _png(color=color)
        response = _upload(client, [(name, body, f"image/{fmt.lower()}")])
        refs.append(response.json()["items"][0]["ref"])

    db = settings.data_dir / DB_FILENAME
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    splits = ["train", "val", "test", "unassigned"]
    labels = ["samoyed", "samoyed", None, "boxer"]
    now = "2026-09-13T00:00:00Z"
    for ref, split, class_id in zip(refs, splits, labels, strict=True):
        conn.execute("UPDATE images SET split = ? WHERE ref = ?", (split, ref))
        if class_id is not None:
            image_id = conn.execute(
                "SELECT id FROM images WHERE ref = ?", (ref,)
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO labels (image_id, class_id, source, created_at)
                VALUES (?, ?, 'human', ?)
                """,
                (img_id := image_id, class_id, now),
            )
            del img_id
    conn.commit()
    conn.close()

    labeled = client.get("/api/images", params={"labeled": True})
    assert labeled.status_code == 200
    assert labeled.json()["total"] == 3
    assert len(labeled.json()["items"]) == 3

    samoyed_train = client.get(
        "/api/images", params={"split": "train", "class_id": "samoyed", "labeled": True}
    )
    assert samoyed_train.json()["total"] == 1
    assert samoyed_train.json()["items"][0]["ref"] == refs[0]

    unlabeled = client.get("/api/images", params={"labeled": False})
    assert unlabeled.json()["total"] == 1
    assert unlabeled.json()["items"][0]["ref"] == refs[2]

    page1 = client.get("/api/images", params={"limit": 2, "offset": 0})
    page2 = client.get("/api/images", params={"limit": 2, "offset": 2})
    again = client.get("/api/images", params={"limit": 2, "offset": 0})
    full = client.get("/api/images")
    assert page1.json()["total"] == 4
    assert full.json()["total"] == 4
    assert page1.json()["items"] == full.json()["items"][:2]
    assert page2.json()["items"] == full.json()["items"][2:]
    assert page1.json()["items"] == again.json()["items"]
    state_refs = [item["ref"] for item in _state_images(client)]
    assert [item["ref"] for item in full.json()["items"]] == state_refs


def test_ver_f_img_005_delete_cascade_and_path_traversal(
    client: TestClient, settings: Settings, tmp_path: Path
) -> None:
    """VER-F-IMG-005: 削除で関連が消え、パス横断ファイル名でも範囲外に書かない。"""
    jpeg = _jpeg(size=(40, 10), color=(3, 3, 3))
    sneaky = _upload(
        client,
        [("../../../etc/passwd.jpg", jpeg, "image/jpeg")],
    )
    assert sneaky.status_code == 200
    ref = sneaky.json()["items"][0]["ref"]
    detail = client.get(f"/api/images/{ref}").json()
    assert detail["original_name"] == "../../../etc/passwd.jpg"

    created = [p for p in tmp_path.rglob("*") if p.is_file()]
    for path in created:
        assert path.is_relative_to(settings.data_dir)
    assert not (tmp_path / "etc" / "passwd.jpg").exists()
    assert not (tmp_path.parent / "etc" / "passwd.jpg").exists()
    image_files = list((settings.data_dir / "images").iterdir())
    assert image_files
    for path in image_files:
        mode = path.stat().st_mode
        assert not (mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

    db = settings.data_dir / DB_FILENAME
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    now = "2026-09-13T00:00:00Z"
    image_id = conn.execute("SELECT id FROM images WHERE ref = ?", (ref,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO models (ref, version, builtin, active, created_at)
        VALUES (?, 1, 0, 0, ?)
        """,
        ("11111111-bbbb-4ccc-8ddd-eeeeeeeeeeee", now),
    )
    model_id = conn.execute("SELECT id FROM models WHERE version = 1").fetchone()[0]
    conn.execute(
        """
        INSERT INTO labels (image_id, class_id, source, created_at)
        VALUES (?, 'samoyed', 'human', ?)
        """,
        (image_id, now),
    )
    conn.execute(
        """
        INSERT INTO inferences (
            ref, image_id, model_id, top_class_id, top_confidence,
            other_mass, low_confidence, scores_json, created_at
        )
        VALUES (?, ?, ?, 'samoyed', 0.9, NULL, 0, '[]', ?)
        """,
        ("22222222-bbbb-4ccc-8ddd-eeeeeeeeeeee", image_id, model_id, now),
    )
    conn.commit()
    conn.close()

    state_before = client.get("/api/_state").json()
    assert len(state_before["images"]) == 1
    assert state_before["images"][0]["label"]["class_id"] == "samoyed"
    assert len(state_before["inferences"]) == 1
    assert len(state_before["models"]) == 1

    deleted = client.delete(f"/api/images/{ref}")
    assert deleted.status_code == 204
    state_after = client.get("/api/_state").json()
    assert state_after["images"] == []
    assert state_after["inferences"] == []
    assert len(state_after["models"]) == 1
    assert list((settings.data_dir / "images").iterdir()) == []
    assert list((settings.data_dir / "thumbs").iterdir()) == []

    missing = client.delete(f"/api/images/{ref}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "image_not_found"


def test_thumbnail_keeps_aspect_ratio(client: TestClient) -> None:
    """REQ-F-IMG-007: 長辺 256 以下、アスペクト比保持。"""
    payload = _jpeg(size=(400, 100), color=(8, 8, 8))
    response = _upload(client, [("wide.jpg", payload, "image/jpeg")])
    ref = response.json()["items"][0]["ref"]
    thumb = client.get(f"/api/images/{ref}/thumbnail")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/jpeg")
    image = Image.open(io.BytesIO(thumb.content))
    assert max(image.size) == THUMB_LONG_EDGE
    assert image.size == (256, 64)


def test_decode_failure_is_rejected_and_process_continues(client: TestClient) -> None:
    """REQ-ATT-REL-003: デコード不能は拒否して継続する。"""
    truncated = b"\xff\xd8\xff" + b"\x00" * 32
    failed = _upload(client, [("bad.jpg", truncated, "image/jpeg")])
    assert failed.status_code == 415
    alive = client.get("/api/_state")
    assert alive.status_code == 200
    ok = _upload(client, [("ok.jpg", _jpeg(), "image/jpeg")])
    assert ok.status_code == 200
    assert len(_state_images(client)) == 1


def test_empty_upload_is_validation_error(client: TestClient) -> None:
    response = client.post("/api/images")
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_invalid_list_query_is_validation_error(client: TestClient) -> None:
    response = client.get("/api/images", params={"limit": 0})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    response = client.get("/api/images", params={"split": "nope"})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_missing_image_is_not_found(client: TestClient) -> None:
    ref = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    detail = client.get(f"/api/images/{ref}")
    assert detail.status_code == 404
    assert detail.json()["code"] == "image_not_found"
    thumb = client.get(f"/api/images/{ref}/thumbnail")
    assert thumb.status_code == 404
    assert thumb.json()["code"] == "image_not_found"


def test_single_duplicate_is_conflict(client: TestClient) -> None:
    payload = _jpeg(color=(12, 13, 14))
    first = _upload(client, [("a.jpg", payload, "image/jpeg")])
    assert first.status_code == 200
    second = _upload(client, [("b.jpg", payload, "image/jpeg")])
    assert second.status_code == 409
    assert second.json()["code"] == "image_duplicate"


def test_too_many_files_is_validation_error(client: TestClient) -> None:
    tiny = _jpeg(size=(8, 8))
    files = [("files", (f"{index}.jpg", tiny, "image/jpeg")) for index in range(51)]
    response = client.post("/api/images", files=files)
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_detail_and_list_include_metadata(client: TestClient) -> None:
    payload = _png(size=(20, 10), color=(1, 2, 3))
    uploaded = _upload(client, [("dog.png", payload, "image/png")])
    ref = uploaded.json()["items"][0]["ref"]
    detail = client.get(f"/api/images/{ref}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["original_name"] == "dog.png"
    assert body["media_type"] == "image/png"
    assert body["width"] == 20
    assert body["height"] == 10
    listed = client.get("/api/images")
    assert listed.json()["items"][0]["ref"] == ref
    assert listed.json()["items"][0]["sha256"] == body["sha256"]


def test_delete_removes_suggestion(client: TestClient, settings: Settings) -> None:
    payload = _jpeg(color=(2, 4, 6))
    uploaded = _upload(client, [("s.jpg", payload, "image/jpeg")])
    ref = uploaded.json()["items"][0]["ref"]
    db = settings.data_dir / DB_FILENAME
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    now = "2026-09-13T00:00:00Z"
    image_id = conn.execute("SELECT id FROM images WHERE ref = ?", (ref,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO models (ref, version, builtin, active, created_at)
        VALUES (?, 1, 0, 0, ?)
        """,
        ("33333333-bbbb-4ccc-8ddd-eeeeeeeeeeee", now),
    )
    model_id = conn.execute("SELECT id FROM models WHERE version = 1").fetchone()[0]
    conn.execute(
        """
        INSERT INTO suggestions (image_id, class_id, confidence, model_id, created_at)
        VALUES (?, 'boxer', 0.8, ?, ?)
        """,
        (image_id, model_id, now),
    )
    conn.commit()
    conn.close()
    suggestion = client.get("/api/_state").json()["images"][0]["suggestion"]
    assert suggestion["class_id"] == "boxer"
    assert client.delete(f"/api/images/{ref}").status_code == 204
    state = client.get("/api/_state").json()
    assert state["images"] == []
    assert state["models"][0]["version"] == 1


def test_upload_writes_files_before_publishing_ref(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserted = {"done": False}
    real_insert = Store.insert_image

    def insert(self: Store, **kwargs: Any) -> None:
        inserted["done"] = True
        real_insert(self, **kwargs)

    def write(root: Path, relative: str, data: bytes) -> Path:
        assert inserted["done"] is False
        from faunalab.persist.files import write_bytes as real_write

        return real_write(root, relative, data)

    monkeypatch.setattr("faunalab.persist.store.Store.insert_image", insert)
    monkeypatch.setattr("faunalab.api.images.write_bytes", write)
    uploaded = _upload(client, [("order.jpg", _jpeg(color=(9, 8, 7)), "image/jpeg")])
    assert uploaded.status_code == 200
    assert uploaded.json()["items"][0]["ok"] is True
    assert inserted["done"] is True
    assert list((settings.data_dir / "images").iterdir())
    assert list((settings.data_dir / "thumbs").iterdir())


def test_duplicate_insert_does_not_remove_winner_files(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _jpeg(color=(7, 8, 9))
    first = _upload(client, [("a.jpg", payload, "image/jpeg")])
    assert first.status_code == 200
    images_before = sorted(p.name for p in (settings.data_dir / "images").iterdir())
    thumbs_before = sorted(p.name for p in (settings.data_dir / "thumbs").iterdir())
    monkeypatch.setattr(
        "faunalab.persist.store.Store.sha256_exists",
        lambda self, sha256: False,
    )
    second = _upload(client, [("b.jpg", payload, "image/jpeg")])
    assert second.status_code == 409
    assert second.json()["code"] == "image_duplicate"
    image_names = sorted(p.name for p in (settings.data_dir / "images").iterdir())
    thumb_names = sorted(p.name for p in (settings.data_dir / "thumbs").iterdir())
    assert image_names == images_before
    assert thumb_names == thumbs_before
    assert len(_state_images(client)) == 1


def test_delete_succeeds_when_file_unlink_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _jpeg(color=(1, 2, 4))
    uploaded = _upload(client, [("keep.jpg", payload, "image/jpeg")])
    ref = uploaded.json()["items"][0]["ref"]

    def boom(_root: Path, _relative: str) -> None:
        raise OSError("busy")

    monkeypatch.setattr("faunalab.api.images.remove_if_present", boom)
    deleted = client.delete(f"/api/images/{ref}")
    assert deleted.status_code == 204
    assert _state_images(client) == []
