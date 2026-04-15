"""
素材模块测试
"""
import json
import re
from datetime import datetime

import pytest
from app.ai import minimax_client
from app.material import service as material_service
from app.material.schemas import POLISH_STYLES
from app.models.material import RawMaterial
from tests.conftest import create_test_user, get_auth_header


def test_create_material_text(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/materials", json={
        "type": "text",
        "content": "今天天气很好，心情愉快！",
        "date": "2026-03-25",
    }, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    m = data["data"]
    # 验证 camelCase 字段
    assert "userId" in m
    assert "mediaUrl" in m
    assert "thumbnailUrl" in m
    assert "createdAt" in m
    assert m["type"] == "text"
    assert m["content"] == "今天天气很好，心情愉快！"


def test_create_material_id_and_date_generation_rule(client):
    """id=年月日时分秒+userId；date=YYYY-MM-DD HH:MM:SS"""
    user_data = create_test_user(client, username="mat_id_rule")
    headers = get_auth_header(user_data["token"])

    resp = client.post("/api/materials", json={
        "type": "text",
        "content": "规则测试",
        "date": "2026-03-25",
    }, headers=headers)

    assert resp.status_code == 200
    m = resp.json()["data"]
    user_id = user_data["user"]["id"]

    assert re.match(rf"^\d{{14}}_{re.escape(user_id)}(?:_\d+)?$", m["id"])
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", m["date"])
    assert m["date"].startswith("2026-03-25 ")


def test_create_material_dedup_within_one_second(client, monkeypatch):
    """同用户同负载 1s 内重复创建：返回同一条素材，不重复入库。"""
    user_data = create_test_user(client, username="material_dedup_user")
    headers = get_auth_header(user_data["token"])

    base_dt = datetime(2026, 3, 25, 9, 8, 7)
    base_ms = int(base_dt.timestamp() * 1000)
    ms_values = iter([base_ms, base_ms + 500])
    dt_values = iter([base_dt, base_dt])

    monkeypatch.setattr(material_service, "_now_ms", lambda: next(ms_values))
    monkeypatch.setattr(material_service, "_now_dt", lambda: next(dt_values))

    payload = {
        "type": "text",
        "content": "短时间重复点击",
        "date": "2026-03-25",
    }
    first = client.post("/api/materials", json=payload, headers=headers)
    second = client.post("/api/materials", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200

    first_data = first.json()["data"]
    second_data = second.json()["data"]
    assert first_data["id"] == second_data["id"]

    listed = client.get("/api/materials?date=2026-03-25", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1


def test_create_material_accepts_camelcase_fields(client):
    """创建素材请求支持 camelCase（前端直传）。"""
    user_data = create_test_user(client, username="mat_camel_user")
    headers = get_auth_header(user_data["token"])

    payload = {
        "type": "image",
        "content": "camelCase 测试",
        "mediaUrl": ["/uploads/mock/image.jpg", "/uploads/mock/image2.jpg"],
        "thumbnailUrl": ["/uploads/mock/thumb.jpg", "/uploads/mock/thumb2.jpg"],
        "location": {"lat": 39.1, "lng": 117.2, "address": "天津"},
        "date": "2026-03-25",
    }
    resp = client.post("/api/materials", json=payload, headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mediaUrl"] == payload["mediaUrl"]
    assert data["thumbnailUrl"] == payload["thumbnailUrl"]
    assert data["location"] == payload["location"]


def test_create_material_accepts_legacy_string_media_url(client):
    """兼容旧端：mediaUrl 传 string 时自动归一为数组。"""
    user_data = create_test_user(client, username="mat_legacy_media")
    headers = get_auth_header(user_data["token"])

    payload = {
        "type": "image",
        "content": "旧字段兼容",
        "mediaUrl": "/uploads/mock/legacy.jpg",
        "date": "2026-03-25",
    }
    resp = client.post("/api/materials", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mediaUrl"] == [payload["mediaUrl"]]


def test_create_material_accepts_legacy_string_thumbnail_url(client):
    """兼容旧端：thumbnailUrl 传 string 时自动归一为数组。"""
    user_data = create_test_user(client, username="mat_legacy_thumb")
    headers = get_auth_header(user_data["token"])

    payload = {
        "type": "image",
        "content": "缩略图旧字段兼容",
        "mediaUrl": ["/uploads/mock/legacy-thumb.jpg"],
        "thumbnailUrl": "/uploads/mock/thumb-legacy.jpg",
        "date": "2026-03-25",
    }
    resp = client.post("/api/materials", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["thumbnailUrl"] == [payload["thumbnailUrl"]]


def test_create_material_image_flow_with_uploaded_url(client):
    """image 素材先走 /upload/diary-image，再用返回 URL 创建 /materials 记录。"""
    user_data = create_test_user(client, username="material_image_user")
    headers = get_auth_header(user_data["token"])

    upload_resp = client.post(
        "/api/upload/diary-image",
        files={"file": ("diary.png", b"fake-image-bytes", "image/png")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    assert upload_data["code"] == 0

    image_url = upload_data["data"]["url"]
    thumbnail_url = upload_data["data"]["thumbnailUrl"]
    location = upload_data["data"]["location"]
    assert image_url.startswith("/uploads/")
    assert thumbnail_url
    assert isinstance(location, dict)

    create_resp = client.post(
        "/api/materials",
        json={
            "type": "image",
            "content": "今天拍到了晚霞",
            "media_url": [image_url],
            "date": "2026-03-25",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    data = create_resp.json()["data"]
    assert data["type"] == "image"
    assert data["mediaUrl"] == [image_url]
    assert data["thumbnailUrl"] == [thumbnail_url]
    assert data["location"] == location
    assert data["content"] == "今天拍到了晚霞"


def test_create_material_with_multiple_uploaded_images(client):
    """多图场景：可传 mediaUrl 数组并按顺序保存。"""
    user_data = create_test_user(client, username="mat_multi_img")
    headers = get_auth_header(user_data["token"])

    upload1 = client.post(
        "/api/upload/diary-image",
        files={"file": ("img1.png", b"fake-image-1", "image/png")},
        headers=headers,
    )
    upload2 = client.post(
        "/api/upload/diary-image",
        files={"file": ("img2.png", b"fake-image-2", "image/png")},
        headers=headers,
    )

    assert upload1.status_code == 200
    assert upload2.status_code == 200

    image_url1 = upload1.json()["data"]["url"]
    image_url2 = upload2.json()["data"]["url"]
    thumbnail1 = upload1.json()["data"]["thumbnailUrl"]
    thumbnail2 = upload2.json()["data"]["thumbnailUrl"]
    location1 = upload1.json()["data"]["location"]

    create_resp = client.post(
        "/api/materials",
        json={
            "type": "image",
            "content": "今天拍了两张图",
            "mediaUrl": [image_url1, image_url2],
            "date": "2026-03-25",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200

    data = create_resp.json()["data"]
    assert data["type"] == "image"
    assert data["mediaUrl"] == [image_url1, image_url2]
    assert data["thumbnailUrl"] == [thumbnail1, thumbnail2]
    assert data["location"] == location1


def test_batch_upload_diary_images_flow(client):
    """批量上传接口可一次上传多张并用于创建素材。"""
    user_data = create_test_user(client, username="mat_batch_up")
    headers = get_auth_header(user_data["token"])

    upload_resp = client.post(
        "/api/upload/diary-images",
        files=[
            ("files", ("img1.png", b"fake-image-1", "image/png")),
            ("files", ("img2.png", b"fake-image-2", "image/png")),
        ],
        headers=headers,
    )

    assert upload_resp.status_code == 200
    payload = upload_resp.json()
    assert payload["code"] == 0

    items = payload["data"]["items"]
    assert isinstance(items, list)
    assert len(items) == 2
    assert items[0]["url"].startswith("/uploads/")
    assert items[1]["url"].startswith("/uploads/")
    assert items[0]["thumbnailUrl"]
    assert isinstance(items[0]["location"], dict)

    create_resp = client.post(
        "/api/materials",
        json={
            "type": "image",
            "content": "批量上传后的多图素材",
            "mediaUrl": [item["url"] for item in items],
            "date": "2026-03-25",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    assert created["mediaUrl"] == [item["url"] for item in items]


def test_batch_upload_diary_images_limit(client):
    """批量上传超过上限时应返回 400。"""
    user_data = create_test_user(client, username="mat_batch_lim")
    headers = get_auth_header(user_data["token"])

    files = [("files", (f"img{i}.png", b"x", "image/png")) for i in range(10)]
    resp = client.post("/api/upload/diary-images", files=files, headers=headers)

    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] != 0
    assert "最多上传" in body["message"]


def test_create_material_voice_flow(client):
    """voice 素材先拿到语音 URL/转写，再创建 /materials 记录。"""
    user_data = create_test_user(client, username="material_voice_user")
    headers = get_auth_header(user_data["token"])

    voice_resp = client.post(
        "/api/materials/voice",
        files={"file": ("voice.m4a", b"fake-audio-bytes", "audio/m4a")},
        headers=headers,
    )
    assert voice_resp.status_code == 200
    voice_data = voice_resp.json()
    assert voice_data["code"] == 0

    voice_url = voice_data["data"]["url"]
    transcription = voice_data["data"]["transcription"]
    assert voice_url
    assert transcription

    create_resp = client.post(
        "/api/materials",
        json={
            "type": "voice",
            "content": transcription,
            "media_url": [voice_url],
            "date": "2026-03-25",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    data = create_resp.json()["data"]
    assert data["type"] == "voice"
    assert data["content"] == transcription
    assert data["mediaUrl"] == [voice_url]


def test_upload_chat_file(client):
    """聊天文件附件单独上传，返回完整文件元信息。"""
    user_data = create_test_user(client, username="chat_file_user")
    headers = get_auth_header(user_data["token"])

    resp = client.post(
        "/api/upload/chat-file",
        files={"file": ("notes.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["url"].startswith("/uploads/")
    assert data["name"] == "notes.pdf"
    assert data["mimeType"] == "application/pdf"


def test_list_materials_bare_array(client):
    """GET /materials?date= 返回裸数组"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    # 创建 2 条素材
    for i in range(2):
        client.post("/api/materials", json={
            "type": "text",
            "content": f"素材 {i}",
            "date": "2026-03-25",
        }, headers=headers)

    resp = client.get("/api/materials?date=2026-03-25", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    # 应该是裸数组，不是 {items, total}
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 2


def test_get_material_detail(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "详情测试",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.get(f"/api/materials/{material_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert resp.json()["data"]["id"] == material_id


def test_update_material(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "原始内容",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.put(f"/api/materials/{material_id}", json={
        "content": "更新后的内容",
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == "更新后的内容"


def test_update_material_json_fields_roundtrip(client, db):
    """JSON 字段更新后：数据库存字符串，接口返回 dict/list"""
    user_data = create_test_user(client, username="material_json_user")
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "JSON 更新测试",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    payload = {
        "location": {"lat": 39.12, "lng": 117.20, "address": "天津南开大学"},
        "emotion": {"label": "开心", "score": 0.91, "emoji": "😊"},
        "tags": ["校园", "复习"],
    }

    update_resp = client.put(f"/api/materials/{material_id}", json=payload, headers=headers)
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]

    # API 层应返回解码后的 dict/list
    assert isinstance(updated["location"], dict)
    assert isinstance(updated["emotion"], dict)
    assert isinstance(updated["tags"], list)
    assert updated["location"] == payload["location"]
    assert updated["emotion"] == payload["emotion"]
    assert updated["tags"] == payload["tags"]

    # DB 层应保存为 JSON 字符串
    m = db.query(RawMaterial).filter(RawMaterial.id == material_id).first()
    assert m is not None
    assert isinstance(m.location, str)
    assert isinstance(m.emotion, str)
    assert isinstance(m.tags, str)
    assert json.loads(m.location) == payload["location"]
    assert json.loads(m.emotion) == payload["emotion"]
    assert json.loads(m.tags) == payload["tags"]

    # 再次查询详情，确认读取时仍能正确反序列化
    detail_resp = client.get(f"/api/materials/{material_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["location"] == payload["location"]
    assert detail["emotion"] == payload["emotion"]
    assert detail["tags"] == payload["tags"]


def test_update_material_partial_json_keeps_unset_fields(client, db):
    """只更新部分 JSON 字段时，未传字段应保持原值"""
    user_data = create_test_user(client, username="mat_json_partial")
    headers = get_auth_header(user_data["token"])

    original_location = {"lat": 39.10, "lng": 117.17, "address": "原始地点"}
    original_emotion = {"label": "平静", "score": 0.55, "emoji": "😌"}
    original_tags = ["原始标签", "复习"]

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "部分更新测试",
        "date": "2026-03-25",
        "location": original_location,
        "emotion": original_emotion,
        "tags": original_tags,
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    new_emotion = {"label": "开心", "score": 0.92, "emoji": "😊"}
    update_resp = client.put(
        f"/api/materials/{material_id}",
        json={"emotion": new_emotion},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]

    # 仅 emotion 被更新，location/tags 保持原值
    assert updated["emotion"] == new_emotion
    assert updated["location"] == original_location
    assert updated["tags"] == original_tags

    # DB 层校验：未传字段不应被覆盖
    m = db.query(RawMaterial).filter(RawMaterial.id == material_id).first()
    assert m is not None
    assert json.loads(m.emotion) == new_emotion
    assert json.loads(m.location) == original_location
    assert json.loads(m.tags) == original_tags


def test_delete_material(client):
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "待删除",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.delete(f"/api/materials/{material_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] is None


def test_emotion_extraction_mock_format(client, db, monkeypatch):
    """POST /materials/{id}/emotion 在 Mock 下返回情绪结构并写回数据库"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    class FakeMiniMaxClient:
        async def extract_emotion(self, text: str):
            return {"label": "开心", "score": 0.88, "emoji": "😊"}

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "今天很开心，考试考得不错！",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/materials/{material_id}/emotion", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    # 结构校验：不写死具体值，只校验字段与类型
    assert set(data.keys()) == {"label", "score", "emoji"}
    assert isinstance(data["label"], str) and data["label"]
    assert isinstance(data["score"], (int, float))
    assert 0 <= float(data["score"]) <= 1
    assert isinstance(data["emoji"], str) and data["emoji"]

    # 写库校验：emotion 以 JSON string 持久化
    m = db.query(RawMaterial).filter(RawMaterial.id == material_id).first()
    assert m is not None
    assert json.loads(m.emotion) == data


def test_create_material_auto_emotion_cry_keyword_not_calm(client, monkeypatch):
    """创建素材自动情绪提取：'想哭' 应优先识别为难过。"""
    user_data = create_test_user(client, username="mat_auto_emotion_cry")
    headers = get_auth_header(user_data["token"])

    monkeypatch.setattr(minimax_client.settings, "MINIMAX_MOCK", True)
    monkeypatch.setattr(minimax_client, "_minimax_client", None)

    resp = client.post(
        "/api/materials",
        json={
            "type": "text",
            "content": "今天真的有点想哭，心里很难受",
            "date": "2026-03-25",
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["emotion"]["label"] == "难过"
    assert data["emotion"]["emoji"] == "😢"


@pytest.mark.parametrize("style", POLISH_STYLES)
def test_polish_text_returns_only_polished(client, monkeypatch, style):
    """POST /materials/{id}/polish 按配置风格遍历，且只返回 {polished}"""
    user_data = create_test_user(client)
    headers = get_auth_header(user_data["token"])

    expected_polished = "润色后的文字"

    class FakeMiniMaxClient:
        async def polish_text(self, text: str, style_name: str):
            assert style_name in POLISH_STYLES
            return expected_polished

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

    create_resp = client.post("/api/materials", json={
        "type": "text",
        "content": "今天学习了很多东西",
        "date": "2026-03-25",
    }, headers=headers)
    material_id = create_resp.json()["data"]["id"]

    resp = client.post(f"/api/materials/{material_id}/polish", json={
        "style": style
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"polished": expected_polished}
    assert len(data.keys()) == 1


def test_material_no_auth(client):
    resp = client.get("/api/materials")
    assert resp.status_code == 401 or resp.json().get("code", 0) != 0
