"""记忆系统 API 集成测试。"""
import json
import time

from app.memory.service import create_memory_document
from app.models.memory import MemoryFact
from tests.conftest import create_test_user, get_auth_header


def _seed_memory_document(db, user_id: str, source_id: str, content: str, **kwargs):
    document = create_memory_document(
        db,
        user_id=user_id,
        source_type=kwargs.pop("source_type", "diary"),
        source_id=source_id,
        title=kwargs.pop("title", "测试记忆"),
        content=content,
        summary=kwargs.pop("summary", content[:40]),
        visibility=kwargs.pop("visibility", "private"),
        memory_scope=kwargs.pop("memory_scope", "self"),
        tags=kwargs.pop("tags", ["测试"]),
        occurred_at=kwargs.pop("occurred_at", int(time.time() * 1000)),
    )
    db.commit()
    return document


def test_search_documents_and_delete_memory_flow(client, db):
    user_data = create_test_user(client, username="memory_api_search")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]

    document = _seed_memory_document(
        db,
        user_id,
        "diary-search-1",
        "今天在图书馆学习数据库，还记下了很多关于检索的想法。",
        title="图书馆学习",
    )

    search_resp = client.post(
        "/api/memory/search",
        json={"query": "图书馆 检索", "scenario": "chat", "topK": 5},
        headers=headers,
    )
    assert search_resp.status_code == 200
    items = search_resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["documentId"] == document.id
    assert items[0]["title"] == "图书馆学习"

    list_resp = client.get("/api/memory/documents?sourceType=diary", headers=headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()["data"]["items"]
    assert len(listed) == 1
    assert listed[0]["id"] == document.id
    assert listed[0]["tags"] == ["测试"]

    detail_resp = client.get(f"/api/memory/documents/{document.id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["content"].startswith("今天在图书馆学习数据库")

    delete_resp = client.delete(f"/api/memory/documents/{document.id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"] is None

    detail_404_resp = client.get(f"/api/memory/documents/{document.id}", headers=headers)
    assert detail_404_resp.status_code == 404


def test_extract_list_and_update_facts(client, db, monkeypatch):
    from app.ai import minimax_client

    class FakeMiniMaxClient:
        mock = False

        async def chat_completion(self, messages, system_prompt="", temperature=0.2, max_tokens=1200):
            return json.dumps(
                {
                    "facts": [
                        {
                            "category": "interest",
                            "content": "用户喜欢夜跑",
                            "subject": "用户",
                            "predicate": "likes",
                            "object": "夜跑",
                            "confidence": 0.92,
                            "stability": "stable",
                        },
                        {
                            "category": "boundary",
                            "content": "用户不喜欢高压力社交",
                            "subject": "用户",
                            "predicate": "dislikes",
                            "object": "高压力社交",
                            "confidence": 0.88,
                            "stability": "stable",
                        },
                    ]
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

    user_data = create_test_user(client, username="memory_api_extract")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]
    document = _seed_memory_document(
        db,
        user_id,
        "diary-extract-1",
        "我最近喜欢夜跑，但不喜欢太高压力的社交场合。",
        title="夜跑与社交",
    )

    extract_resp = client.post(f"/api/memory/documents/{document.id}/extract", headers=headers)
    assert extract_resp.status_code == 200
    items = extract_resp.json()["data"]["items"]
    assert len(items) == 2
    assert {item["category"] for item in items} == {"interest", "boundary"}

    facts_resp = client.get("/api/memory/facts?activeOnly=true", headers=headers)
    assert facts_resp.status_code == 200
    facts = facts_resp.json()["data"]["items"]
    assert len(facts) == 2

    fact_id = facts[0]["id"]
    update_resp = client.put(
        f"/api/memory/facts/{fact_id}",
        json={"content": "用户很喜欢夜跑", "isPinned": True},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["content"] == "用户很喜欢夜跑"
    assert updated["isPinned"] is True

    boundary_resp = client.get("/api/memory/facts?category=boundary", headers=headers)
    assert boundary_resp.status_code == 200
    assert len(boundary_resp.json()["data"]["items"]) == 1

    assert db.query(MemoryFact).filter(MemoryFact.user_id == user_id).count() == 2


def test_manual_fact_create_update_and_delete(client, db):
    user_data = create_test_user(client, username="memory_manual_fact")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]

    create_resp = client.post(
        "/api/memory/facts",
        json={
            "category": "interest",
            "content": "用户喜欢在傍晚散步",
            "confidence": 0.95,
            "isPinned": True,
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    assert created["category"] == "interest"
    assert created["content"] == "用户喜欢在傍晚散步"
    assert created["isPinned"] is True
    assert created["confidence"] == 0.95

    fact_id = created["id"]
    update_resp = client.put(
        f"/api/memory/facts/{fact_id}",
        json={"category": "habit", "content": "用户常在傍晚散步", "confidence": 0.88},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()["data"]
    assert updated["category"] == "habit"
    assert updated["confidence"] == 0.88

    delete_resp = client.delete(f"/api/memory/facts/{fact_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert db.query(MemoryFact).filter(MemoryFact.user_id == user_id).count() == 0


def test_regenerate_memory_profile_api(client, db, monkeypatch):
    from app.ai import minimax_client

    class FakeMiniMaxClient:
        mock = False

        async def chat_completion(self, messages, system_prompt="", temperature=0.3, max_tokens=1600):
            return json.dumps(
                {
                    "summary": "这是一个偏安静、但愿意慢慢建立连接的用户。",
                    "traits": {"introversion": "medium"},
                    "interests": ["摄影", "夜跑"],
                    "preferences": {"social": "low_pressure"},
                    "relations": {"close_friends": 2},
                    "social_style": {"tone": "自然"},
                    "boundaries": ["不喜欢高压力社交"],
                    "recent_state": "最近在尝试恢复规律生活",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: FakeMiniMaxClient())

    user_data = create_test_user(client, username="memory_api_profile")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]

    _seed_memory_document(
        db,
        user_id,
        "diary-profile-1",
        "这周开始重新夜跑，也想把生活节奏调整回来。",
        title="重启规律生活",
    )

    now = int(time.time() * 1000)
    db.add(
        MemoryFact(
            id="fact-profile-1",
            user_id=user_id,
            category="interest",
            content="用户喜欢摄影",
            subject="用户",
            predicate="likes",
            object="摄影",
            confidence=0.9,
            stability="stable",
            evidence_document_id=None,
            evidence_chunk_id=None,
            source_type="manual",
            valid_from=now,
            valid_to=None,
            is_active=True,
            is_pinned=True,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()

    resp = client.post("/api/memory/profile/regenerate?profileType=avatar", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["profileType"] == "avatar"
    assert data["summary"] == "这是一个偏安静、但愿意慢慢建立连接的用户。"
    assert data["interests"] == ["摄影", "夜跑"]
    assert data["boundaries"] == ["不喜欢高压力社交"]
    assert data["sourceRange"]["document_count"] >= 1


def test_export_and_delete_all_memories(client, db):
    user_data = create_test_user(client, username="memory_api_export")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]

    document = _seed_memory_document(
        db,
        user_id,
        "diary-export-1",
        "今天想认真整理一下自己的长期记忆。",
        title="整理记忆",
    )
    now = int(time.time() * 1000)
    db.add(
        MemoryFact(
            id="fact-export-1",
            user_id=user_id,
            category="habit",
            content="用户会整理长期记忆",
            subject="用户",
            predicate="does",
            object="整理长期记忆",
            confidence=0.8,
            stability="recent",
            evidence_document_id=document.id,
            evidence_chunk_id=None,
            source_type="diary",
            valid_from=now,
            valid_to=None,
            is_active=True,
            is_pinned=False,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()

    export_resp = client.get("/api/memory/export", headers=headers)
    assert export_resp.status_code == 200
    payload = export_resp.json()["data"]
    assert payload["version"] == 1
    assert len(payload["documents"]) == 1
    assert len(payload["facts"]) == 1

    delete_resp = client.delete("/api/memory/all", headers=headers)
    assert delete_resp.status_code == 200

    export_after_delete = client.get("/api/memory/export", headers=headers).json()["data"]
    assert export_after_delete["documents"] == []
    assert export_after_delete["facts"] == []


def test_agent_context_does_not_include_private_raw_memory(client, db):
    from app.models.memory import AvatarCard
    from app.models.user import User
    from uuid import uuid4

    viewer_data = create_test_user(client, username="memory_ctx_viewer", school="南开大学")
    owner_data = create_test_user(client, username="memory_ctx_owner", school="南开大学")
    headers = get_auth_header(viewer_data["token"])
    owner_id = owner_data["user"]["id"]
    now = int(time.time() * 1000)

    db.add(
        AvatarCard(
            id=str(uuid4()),
            user_id=owner_id,
            display_name="安全分身",
            public_summary="喜欢摄影和低压力交流。",
            interest_tags='["摄影"]',
            social_intent='["认识同校朋友"]',
            conversation_style='{"tone":"温和"}',
            boundaries='["不透露日记原文"]',
            visibility="private",
            updated_at=now,
        )
    )
    db.commit()
    _seed_memory_document(
        db,
        owner_id,
        "private-diary-context",
        "我的私密日记原文：今天非常难过，不想被任何人知道。",
        title="私密日记",
        visibility="private",
    )
    _seed_memory_document(
        db,
        owner_id,
        "public-post-context",
        "想找同校朋友一起拍照。",
        title="公开广场索引",
        source_type="plaza_post_index",
        visibility="school",
    )

    resp = client.post(
        "/api/memory/agent-context",
        json={"ownerUserId": owner_id, "query": "拍照 同校", "topK": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    context = resp.json()["data"]
    assert context["avatarCard"]["displayName"] == "安全分身"
    assert context["privacyContract"]["rawPrivateMemoryIncluded"] is False
    joined = json.dumps(context, ensure_ascii=False)
    assert "私密日记原文" not in joined
    assert "今天非常难过" not in joined


def test_memory_conflicts_and_decay_api(client, db):
    user_data = create_test_user(client, username="mem_maint")
    headers = get_auth_header(user_data["token"])
    user_id = user_data["user"]["id"]
    old = int(time.time() * 1000) - 400 * 24 * 60 * 60 * 1000

    db.add_all(
        [
            MemoryFact(
                id="conflict-1",
                user_id=user_id,
                category="preference",
                content="用户喜欢夜跑",
                subject="用户",
                predicate="likes",
                object="运动时间",
                confidence=0.9,
                stability="recent",
                source_type="manual",
                is_active=True,
                is_pinned=False,
                created_at=old,
                updated_at=old,
            ),
            MemoryFact(
                id="conflict-2",
                user_id=user_id,
                category="preference",
                content="用户喜欢晨跑",
                subject="用户",
                predicate="likes",
                object="运动时间",
                confidence=0.8,
                stability="recent",
                source_type="manual",
                is_active=True,
                is_pinned=False,
                created_at=old,
                updated_at=old,
            ),
        ]
    )
    db.commit()

    conflicts_resp = client.get("/api/memory/conflicts", headers=headers)
    assert conflicts_resp.status_code == 200
    assert len(conflicts_resp.json()["data"]["items"]) == 1

    decay_resp = client.post(
        "/api/memory/maintenance/decay",
        json={"olderThanDays": 180, "decayFactor": 0.5, "minConfidence": 0.3},
        headers=headers,
    )
    assert decay_resp.status_code == 200
    result = decay_resp.json()["data"]
    assert result["decayed"] == 2
