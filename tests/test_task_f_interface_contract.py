"""
TASK-F 3.x 接口契约测试
"""

import time
from uuid import uuid4

from app.diary import service as diary_service
from app.models.chat import ChatMessage, ChatSession
from app.models.material import RawMaterial
from app.models.user import UserSettings
from tests.conftest import create_test_user, get_auth_header


def _now_ms() -> int:
    return int(time.time() * 1000)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _ensure_user_settings(db, user_id: str) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = UserSettings(id=str(uuid4()), user_id=user_id)
        db.add(settings)

    settings.chat_material_enabled = True
    settings.chat_silence_threshold = 30
    settings.chat_material_toast = True
    settings.chat_min_rounds = 3
    db.commit()
    db.refresh(settings)
    return settings


def test_chat_contract_contains_meta_only_when_material_generated(client, db):
    user_data = create_test_user(client, username="taskf_meta_user")
    token = user_data["token"]
    user_id = user_data["user"]["id"]
    headers = get_auth_header(token)

    # 先构造一个超时的 open session，且满足最小轮数，以便触发 materialGenerated。
    _ensure_user_settings(db, user_id)
    now = _now_ms()
    old_end = now - 31 * 60 * 1000
    old_session = ChatSession(
        id=str(uuid4()),
        user_id=user_id,
        status="open",
        start_time=old_end - 10 * 60 * 1000,
        end_time=old_end,
        message_count=0,
        date=_today(),
        created_at=old_end - 10 * 60 * 1000,
    )
    db.add(old_session)
    db.flush()

    messages = [
        ("user", "第一句"),
        ("assistant", "回复一"),
        ("user", "第二句"),
        ("assistant", "回复二"),
        ("user", "第三句"),
        ("assistant", "回复三"),
    ]
    ts = old_session.start_time
    for role, content in messages:
        db.add(
            ChatMessage(
                id=str(uuid4()),
                user_id=user_id,
                role=role,
                content=content,
                timestamp=ts,
                session_id=old_session.id,
            )
        )
        ts += 1000
    db.commit()

    resp = client.post("/api/chat", json={"message": "新的消息"}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert isinstance(payload["data"], str)
    assert payload["message"] == "ok"
    assert "meta" in payload
    assert payload["meta"]["materialGenerated"] is True
    assert isinstance(payload["meta"]["materialId"], str)


def test_chat_contract_non_mock_path(client, monkeypatch):
    user_data = create_test_user(client, username="taskf_nonmock_user")
    headers = get_auth_header(user_data["token"])

    class FakeClient:
        async def chat_completion(self, *_args, **_kwargs):
            return "这是非 mock 路径回复"

        async def summarize_chat_session(self, *_args, **_kwargs):
            return {
                "title": "对话记录",
                "summary": "摘要",
                "mood": "平静",
                "mood_emoji": "😐",
                "tags": ["对话"],
            }

        async def detect_duplicate_chat_material(self, *_args, **_kwargs):
            return {
                "is_duplicate": False,
                "duplicate_material_id": None,
                "reason": "test-not-duplicate",
                "confidence": 0.0,
            }

    def fake_get_minimax_client():
        return FakeClient()

    monkeypatch.setattr("app.ai.minimax_client.get_minimax_client", fake_get_minimax_client)

    resp = client.post("/api/chat", json={"message": "测试非mock"}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert payload["data"] == "这是非 mock 路径回复"
    assert payload["message"] == "ok"


def test_chat_skip_material_when_duplicate_detected(client, db, monkeypatch):
    user_data = create_test_user(client, username="taskf_dedup_user")
    token = user_data["token"]
    user_id = user_data["user"]["id"]
    headers = get_auth_header(token)

    today = _today()
    existing = RawMaterial(
        id=str(uuid4()),
        user_id=user_id,
        type="text",
        content="下午骑车去了海河边，顺便吃了点小吃。",
        media_url="",
        thumbnail_url="",
        location="{}",
        emotion='{"label":"开心","score":0.8,"emoji":"😊"}',
        tags='["日常"]',
        date=f"{today} 09:00:00",
        created_at=_now_ms(),
    )
    db.add(existing)
    db.commit()

    _ensure_user_settings(db, user_id)
    now = _now_ms()
    old_end = now - 31 * 60 * 1000
    old_session = ChatSession(
        id=str(uuid4()),
        user_id=user_id,
        status="open",
        start_time=old_end - 5 * 60 * 1000,
        end_time=old_end,
        message_count=0,
        date=today,
        created_at=old_end - 5 * 60 * 1000,
    )
    db.add(old_session)
    db.flush()

    ts = old_session.start_time
    for role, content in [
        ("user", "今天下午我去骑车了"),
        ("assistant", "听起来不错，去哪里了？"),
        ("user", "去了海河边"),
        ("assistant", "风景一定很好"),
        ("user", "还吃了小吃"),
        ("assistant", "真充实"),
    ]:
        db.add(
            ChatMessage(
                id=str(uuid4()),
                user_id=user_id,
                role=role,
                content=content,
                timestamp=ts,
                session_id=old_session.id,
            )
        )
        ts += 1000
    db.commit()

    class FakeClient:
        async def chat_completion(self, *_args, **_kwargs):
            return "收到，你今天安排很满。"

        async def summarize_chat_session(self, *_args, **_kwargs):
            return {
                "title": "海河骑行",
                "summary": "下午骑车去了海河边，顺便吃了点小吃。",
                "mood": "开心",
                "mood_emoji": "😊",
                "tags": ["日常"],
            }

        async def detect_duplicate_chat_material(self, *_args, **_kwargs):
            return {
                "is_duplicate": True,
                "duplicate_material_id": existing.id,
                "reason": "same-event",
                "confidence": 0.95,
            }

    def fake_get_minimax_client():
        return FakeClient()

    monkeypatch.setattr("app.ai.minimax_client.get_minimax_client", fake_get_minimax_client)

    resp = client.post("/api/chat", json={"message": "再帮我总结一下今天"}, headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert isinstance(payload["data"], str)
    assert "meta" not in payload

    chat_materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id, RawMaterial.type == "chat")
        .all()
    )
    assert len(chat_materials) == 0


def test_close_session_contract_shape(client):
    user_data = create_test_user(client, username="taskf_close_user")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/chat/close-session", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    data = payload["data"]
    assert set(data.keys()) == {"sessionClosed", "materialGenerated", "materialId"}


def test_session_messages_contract_shape(client):
    user_data = create_test_user(client, username="taskf_sess_user")
    headers = get_auth_header(user_data["token"])

    send_resp = client.post("/api/chat", json={"message": "会话详情测试"}, headers=headers)
    assert send_resp.status_code == 200

    history_resp = client.get("/api/chat/history?limit=20", headers=headers)
    assert history_resp.status_code == 200
    items = history_resp.json()["data"]["items"]
    session_id = next(
        item["sessionId"]
        for item in items
        if item["role"] == "user" and item["content"] == "会话详情测试"
    )

    resp = client.get(f"/api/chat/session/{session_id}/messages", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert set(payload.keys()) == {"session", "messages"}

    session_obj = payload["session"]
    assert {
        "id",
        "title",
        "summary",
        "startTime",
        "endTime",
        "messageCount",
        "mood",
        "moodEmoji",
    }.issubset(set(session_obj.keys()))

    assert len(payload["messages"]) >= 2
    first = payload["messages"][0]
    assert set(first.keys()) == {"role", "content", "timestamp"}


def test_user_settings_validates_task_f_ranges(client):
    user_data = create_test_user(client, username="taskf_settings_user")
    headers = get_auth_header(user_data["token"])

    resp_threshold = client.post(
        "/api/user/settings",
        json={"chat_silence_threshold": 10},
        headers=headers,
    )
    assert resp_threshold.status_code == 422

    resp_rounds = client.post(
        "/api/user/settings",
        json={"chat_min_rounds": 21},
        headers=headers,
    )
    assert resp_rounds.status_code == 422


def test_materials_contract_includes_chat_fields_for_chat_type(client, db):
    user_data = create_test_user(client, username="taskf_material_user")
    token = user_data["token"]
    user_id = user_data["user"]["id"]
    headers = get_auth_header(token)

    today = _today()
    db.add(
        RawMaterial(
            id=str(uuid4()),
            user_id=user_id,
            type="chat",
            content="对话摘要内容",
            media_url="",
            thumbnail_url="",
            location="{}",
            emotion='{"label":"平静","score":0.8,"emoji":"😌"}',
            tags='["对话"]',
            date=f"{today} 09:00:00",
            created_at=_now_ms(),
            chat_session_id="session-1",
            start_time=1711440180000,
            end_time=1711440900000,
        )
    )
    db.commit()

    resp = client.get(f"/api/materials?date={today}", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0

    chat_item = next(item for item in payload["data"] if item["type"] == "chat")
    assert "chatSessionId" in chat_item
    assert "startTime" in chat_item
    assert "endTime" in chat_item


def test_diary_prompt_contains_task_f_chat_format():
    material = RawMaterial(
        id=str(uuid4()),
        user_id="u1",
        type="chat",
        content="和 AI 聊了今天的学习安排",
        media_url="",
        thumbnail_url="",
        location="{}",
        emotion="{}",
        tags="[]",
        date="2026-04-15",
        created_at=1711440180000,
        start_time=1711440180000,
        end_time=1711440900000,
    )

    build_prompt_text = getattr(diary_service, "_build_materials_prompt_text")
    text = build_prompt_text([material], "2026-04-15")

    assert text.startswith("[对话记录] ")
    assert "(" in text and "~" in text and ")" in text
    assert text.endswith("和 AI 聊了今天的学习安排")
