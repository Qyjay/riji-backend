"""/uploads 静态文件的 Content-Type，避免 webp 被当成 text/plain。"""
import mimetypes
from pathlib import Path

from app.config import settings


def test_webp_mimetype_is_registered():
    guessed, _ = mimetypes.guess_type("probe.webp")
    assert guessed == "image/webp"


def test_avif_mimetype_is_registered():
    guessed, _ = mimetypes.guess_type("probe.avif")
    assert guessed == "image/avif"


def test_static_uploads_webp_content_type(client):
    dest = Path(settings.UPLOAD_DIR) / "mime-probe" / "a.webp"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    try:
        resp = client.get("/uploads/mime-probe/a.webp")
        assert resp.status_code == 200
        assert resp.headers["content-type"].split(";")[0].strip() == "image/webp"
    finally:
        dest.unlink(missing_ok=True)


def test_static_uploads_jpg_content_type(client):
    dest = Path(settings.UPLOAD_DIR) / "mime-probe" / "a.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff\xd8\xff\xd9")
    try:
        resp = client.get("/uploads/mime-probe/a.jpg")
        assert resp.status_code == 200
        assert resp.headers["content-type"].split(";")[0].strip() == "image/jpeg"
    finally:
        dest.unlink(missing_ok=True)
