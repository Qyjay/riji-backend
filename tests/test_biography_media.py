import asyncio
import json
from types import SimpleNamespace

from app.biography import service
from app.models.biography import BiographyChapter


class _Query:
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def count(self):
        return 0

    def first(self):
        return None


class _Db:
    def __init__(self):
        self.added = None
        self.committed = False

    def query(self, *args, **kwargs):
        return _Query()

    def add(self, value):
        self.added = value

    def commit(self):
        self.committed = True

    def refresh(self, value):
        return None


class _ImageClient:
    def __init__(self, image_results):
        self.image_results = iter(image_results)

    async def chat_completion(self, *args, **kwargs):
        return json.dumps({
            "title": "真实的一章",
            "content": "第一段。\n\n第二段。",
            "summary": "一段真实生活。",
        }, ensure_ascii=False)

    async def generate_image(self, *args, **kwargs):
        result = next(self.image_results)
        if isinstance(result, Exception):
            raise result
        return result


def _diaries():
    return [
        SimpleNamespace(
            id=f"d{index}",
            date=f"2026-08-{index + 1:02d}",
            content=f"日记 {index}",
            emotion_summary='{"dominant":"平静"}',
            created_at=1000 + index,
        )
        for index in range(service.CHAPTER_THRESHOLD)
    ]


def _run_generation(monkeypatch, client):
    db = _Db()
    monkeypatch.setattr(service, "_consumed_diary_ids", lambda _db, _uid: set())
    monkeypatch.setattr(service, "_published_diaries", lambda _db, _uid: _diaries())
    monkeypatch.setattr(service, "_build_diary_block", lambda _db, _items: ("日记素材", []))
    monkeypatch.setattr(service, "_build_context_block", lambda _db, _uid, _items: "")

    from app.ai import minimax_client

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: client)
    result = asyncio.run(service.generate_chapter(db, "user-1"))
    return db, result


def test_cover_first_attempt_fails_second_succeeds_and_saves_real_url(monkeypatch):
    real_url = "https://www.avalin.cn/uploads/user-1/biography/cover.webp"
    db, result = _run_generation(
        monkeypatch,
        _ImageClient([RuntimeError("content audit rejected"), real_url]),
    )

    assert db.committed is True
    assert db.added.cover_image_url == real_url
    assert result["cover_image_url"] == real_url
    assert db.added.status == "done"


def test_cover_two_failures_save_empty_and_chapter_still_done(monkeypatch, caplog):
    db, result = _run_generation(
        monkeypatch,
        _ImageClient([RuntimeError("image failed"), "file:///tmp/not-remote.png"]),
    )

    assert db.committed is True
    assert db.added.cover_image_url == ""
    assert result["cover_image_url"] == ""
    assert db.added.status == "done"
    assert "exhausted retries" in caplog.text


def test_old_my_story_cover_is_filtered_from_output():
    chapter = BiographyChapter(
        id="chapter-1",
        user_id="user-1",
        chapter_index=1,
        cover_image_url=(
            "https://placehold.co/1280x720/EEE/31343C"
            "?text=My%20Story&font=roboto"
        ),
        illustrations="[]",
        created_at=1,
        updated_at=1,
    )

    assert service._chapter_to_dict(chapter)["cover_image_url"] == ""


def test_placeholder_illustrations_are_filtered_and_real_url_is_kept():
    real_url = "https://www.avalin.cn/uploads/user-1/comic.webp"
    chapter = BiographyChapter(
        id="chapter-1",
        user_id="user-1",
        chapter_index=1,
        cover_image_url="",
        illustrations=json.dumps([
            {
                "diary_id": "d1",
                "image_url": "https://placehold.co/1024x1024?text=Diary+Comic",
                "anchor_para": 0,
            },
            {
                "diary_id": "d2",
                "image_url": "https://example.com/Diary%20Comic.png",
                "anchor_para": 1,
            },
            {
                "diary_id": "d3",
                "image_url": real_url,
                "anchor_para": 2,
            },
        ]),
        created_at=1,
        updated_at=1,
    )

    assert service._chapter_to_dict(chapter)["illustrations"] == [{
        "diary_id": "d3",
        "image_url": real_url,
        "anchor_para": 2,
    }]
