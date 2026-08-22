"""广场帖子板块分类：AI 判定、关键词兜底、用户显式选择优先。"""
import asyncio
import time
from uuid import uuid4

import pytest

from app.ai import minimax_client
from app.models.plaza import PlazaPost
from app.plaza import classifier
from tests.conftest import TestingSessionLocal, create_test_user, get_auth_header


def _run(coro):
    return asyncio.run(coro)


class _FakeClient:
    """替掉真实 LLM 客户端，单测不打外部 API。"""

    mock = False

    def __init__(self, reply):
        self.reply = reply

    async def chat_completion(self, *_args, **_kwargs):
        if isinstance(self.reply, Exception):
            raise self.reply
        if callable(self.reply):
            return await self.reply()
        return self.reply


def _stub_chat(monkeypatch, reply):
    fake = _FakeClient(reply)
    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake)
    return fake


# ==================== AI 判定 ====================

@pytest.mark.parametrize(
    "label,expected",
    [
        ("找搭子", "buddy"),
        ("求助", "help"),
        ("恋爱", "dating"),
        ("分享", "share"),
    ],
)
def test_ai_label_maps_to_each_section(monkeypatch, label, expected):
    _stub_chat(monkeypatch, label)
    result = _run(classifier.classify_post_type("随便一段正文", []))
    assert result == expected


def test_ai_output_tolerates_punctuation_and_quotes(monkeypatch):
    _stub_chat(monkeypatch, ' "求助"。\n')
    assert _run(classifier.classify_post_type("这门课怎么选", [])) == "help"


def test_ai_output_accepts_enum_key(monkeypatch):
    _stub_chat(monkeypatch, "dating")
    assert _run(classifier.classify_post_type("想认真谈一段感情", [])) == "dating"


# ==================== 兜底链路 ====================

def test_ai_timeout_falls_back_to_keywords(monkeypatch):
    async def slow_reply():
        await asyncio.sleep(1)
        return "分享"

    _stub_chat(monkeypatch, slow_reply)
    monkeypatch.setattr(classifier.settings, "PLAZA_CLASSIFY_TIMEOUT_SEC", 0.05)

    assert _run(classifier.classify_post_type("找个一起打羽毛球的搭子", [])) == "buddy"


def test_ai_error_falls_back_to_keywords(monkeypatch):
    _stub_chat(monkeypatch, RuntimeError("boom"))
    assert _run(classifier.classify_post_type("图书馆丢了饭卡，有人捡到吗", [])) == "help"


def test_ai_illegal_value_falls_back_to_keywords(monkeypatch):
    _stub_chat(monkeypatch, "美食板块")
    assert _run(classifier.classify_post_type("想认真谈一段恋爱", [])) == "dating"


def test_blank_and_unmatched_content_uses_default(monkeypatch):
    _stub_chat(monkeypatch, "找搭子")
    assert _run(classifier.classify_post_type("   ", [], default="share")) == "share"
    assert classifier.classify_by_keywords("嗯", [], default="buddy") == "buddy"


def test_keyword_rules_cover_four_sections():
    assert classifier.classify_by_keywords("周六缺一个剧本杀搭子", []) == "buddy"
    assert classifier.classify_by_keywords("选课系统进不去了怎么办", []) == "help"
    assert classifier.classify_by_keywords("想脱单，希望认识合适的人", []) == "dating"
    assert classifier.classify_by_keywords("分享一下期末复习心得", []) == "share"


def test_keyword_rules_never_collapse_into_one_value():
    samples = [
        "找个一起自习的搭子",
        "谁知道校医院几点上班",
        "暗恋隔壁班同学两年了",
        "今天食堂新窗口的面很好吃，安利一下",
    ]
    results = {classifier.classify_by_keywords(text, []) for text in samples}
    assert len(results) == 4


def test_resolved_value_always_in_enum(monkeypatch):
    _stub_chat(monkeypatch, "完全不相关的输出")
    for text in ["随便写点什么", "", "12345"]:
        assert _run(classifier.classify_post_type(text, [])) in classifier.PLAZA_POST_TYPES


# ==================== 用户显式选择优先 ====================

def test_explicit_choice_wins_over_ai(monkeypatch):
    _stub_chat(monkeypatch, "恋爱")
    result = _run(classifier.resolve_post_type("想认真谈一段恋爱", [], requested="share"))
    assert result == "share"


def test_auto_and_blank_request_trigger_ai(monkeypatch):
    _stub_chat(monkeypatch, "求助")
    assert _run(classifier.resolve_post_type("这门课好过吗", [], requested="auto")) == "help"
    assert _run(classifier.resolve_post_type("这门课好过吗", [], requested="")) == "help"
    assert _run(classifier.resolve_post_type("这门课好过吗", [], requested=None)) == "help"


def test_manual_post_keeps_user_selection(client, monkeypatch):
    _stub_chat(monkeypatch, "恋爱")
    user = create_test_user(client, username="plaza_cls_manual")
    headers = get_auth_header(user["token"])

    response = client.post(
        "/api/plaza/posts",
        json={"type": "share", "content": "想认真谈一段恋爱，希望认识合适的人"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["type"] == "share"


def test_manual_post_without_type_is_classified(client, monkeypatch):
    _stub_chat(monkeypatch, "求助")
    user = create_test_user(client, username="plaza_cls_auto")
    headers = get_auth_header(user["token"])

    response = client.post(
        "/api/plaza/posts",
        json={"type": "auto", "content": "选课系统一直登不上，有人知道怎么办吗"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["type"] == "help"


# ==================== 招募帖两条路径 ====================

def _create_mission(client, headers, mode, description, **overrides):
    now = int(time.time() * 1000)
    payload = {
        "mode": mode,
        "purpose_type": "movie" if mode == "short_term" else "friendship",
        "title": "测试任务",
        "description": description,
        "source": "guided_form",
        "time_window": {"label": "本周末", "startAt": now + 86400000, "endAt": now + 172800000},
        "location": {"label": "南开大学", "radiusKm": 5, "precision": "campus"},
        "headcount": {"current": 1, "wanted": 1, "allowWaitlist": True},
        "budget": {"type": "aa"},
        "must_haves": [],
        "preferences": [],
        "boundaries": [],
        "public_memory_ids": [],
        "permissions": {
            "search": True,
            "atoaProbe": True,
            "draftPost": True,
            "draftReply": True,
            "autoPublish": False,
            "autoConnect": False,
        },
        "search_strategy": "search_then_draft",
        "expires_at": now + 172800000,
    }
    payload.update(overrides)
    response = client.post("/api/social/missions", json=payload, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()["data"]


def test_long_term_recruit_post_is_not_forced_to_dating(client, monkeypatch):
    _stub_chat(monkeypatch, "找搭子")
    user = create_test_user(client, username="plaza_cls_long")
    headers = get_auth_header(user["token"])
    mission = _create_mission(
        client,
        headers,
        "long_term",
        "想找一个能长期一起自习和运动的固定伙伴",
    )

    draft = client.post(
        f"/api/social/missions/{mission['id']}/post-draft",
        headers=headers,
    ).json()["data"]
    assert draft["type"] == "buddy"

    post = client.post(
        f"/api/social/missions/{mission['id']}/publish",
        json={
            "content": draft["content"],
            "type": draft["type"],
            "location": draft["location"],
            "tags": draft["tags"],
            "school_only": draft["schoolOnly"],
            "allow_agent_reply": draft["allowAgentReply"],
        },
        headers=headers,
    ).json()["data"]
    assert post["type"] == "buddy"


def test_recruit_post_follows_content_when_it_is_dating(client, monkeypatch):
    _stub_chat(monkeypatch, "恋爱")
    user = create_test_user(client, username="plaza_cls_dating")
    headers = get_auth_header(user["token"])
    mission = _create_mission(
        client,
        headers,
        "long_term",
        "希望认识一个可以认真谈恋爱的人",
        purpose_type="dating",
    )

    draft = client.post(
        f"/api/social/missions/{mission['id']}/post-draft",
        headers=headers,
    ).json()["data"]
    assert draft["type"] == "dating"


def test_publish_without_type_classifies_final_content(client, monkeypatch):
    _stub_chat(monkeypatch, "求助")
    user = create_test_user(client, username="plaza_cls_publish")
    headers = get_auth_header(user["token"])
    mission = _create_mission(client, headers, "short_term", "周末想找人看科幻电影")

    draft = client.post(
        f"/api/social/missions/{mission['id']}/post-draft",
        headers=headers,
    ).json()["data"]

    post = client.post(
        f"/api/social/missions/{mission['id']}/publish",
        json={
            "content": "转专业手续卡住了，有人办过吗",
            "location": draft["location"],
            "tags": [],
            "school_only": draft["schoolOnly"],
            "allow_agent_reply": draft["allowAgentReply"],
        },
        headers=headers,
    ).json()["data"]
    assert post["type"] == "help"


def test_recruit_post_visibility_rules_survive(client, monkeypatch):
    """公开 / 仅本校规则不受分类改动影响。"""
    _stub_chat(monkeypatch, "找搭子")
    author = create_test_user(client, username="plaza_cls_vis_a", school="南开大学")
    outsider = create_test_user(client, username="plaza_cls_vis_b", school="天津大学")
    author_headers = get_auth_header(author["token"])
    outsider_headers = get_auth_header(outsider["token"])

    public_mission = _create_mission(client, author_headers, "short_term", "周末想找人看科幻电影")
    public_draft = client.post(
        f"/api/social/missions/{public_mission['id']}/post-draft",
        headers=author_headers,
    ).json()["data"]
    assert public_draft["schoolOnly"] is False
    public_post = client.post(
        f"/api/social/missions/{public_mission['id']}/publish",
        json={
            "content": public_draft["content"],
            "type": public_draft["type"],
            "location": public_draft["location"],
            "tags": public_draft["tags"],
            "school_only": public_draft["schoolOnly"],
            "allow_agent_reply": public_draft["allowAgentReply"],
        },
        headers=author_headers,
    ).json()["data"]

    school_mission = _create_mission(
        client,
        author_headers,
        "short_term",
        "只想找同校的人一起看电影",
        preferences=["同校"],
    )
    school_draft = client.post(
        f"/api/social/missions/{school_mission['id']}/post-draft",
        headers=author_headers,
    ).json()["data"]
    assert school_draft["schoolOnly"] is True
    school_post = client.post(
        f"/api/social/missions/{school_mission['id']}/publish",
        json={
            "content": school_draft["content"],
            "type": school_draft["type"],
            "location": school_draft["location"],
            "tags": school_draft["tags"],
            "school_only": school_draft["schoolOnly"],
            "allow_agent_reply": school_draft["allowAgentReply"],
        },
        headers=author_headers,
    ).json()["data"]

    visible_ids = {
        item["id"]
        for item in client.get("/api/plaza/posts", headers=outsider_headers).json()["data"]["items"]
    }
    assert public_post["id"] in visible_ids
    assert school_post["id"] not in visible_ids


# ==================== 存量修正脚本 ====================

def test_reclassify_dry_run_does_not_write(db, client, monkeypatch):
    _stub_chat(monkeypatch, "求助")
    user = create_test_user(client, username="plaza_cls_script")
    post = PlazaPost(
        id=str(uuid4()),
        user_id=user["user"]["id"],
        type="dating",
        content="选课系统进不去了，有人知道怎么办吗",
        tags="[]",
        school_only=False,
        created_at=int(time.time() * 1000),
    )
    db.add(post)
    db.commit()
    post_id = post.id

    from scripts.reclassify_plaza_posts import reclassify

    args = type(
        "Args",
        (),
        {
            "dry_run": True,
            "user_id": None,
            "only_type": None,
            "only_agent_posts": False,
            "limit": 0,
            "keywords_only": True,
        },
    )()

    monkeypatch.setattr("scripts.reclassify_plaza_posts.SessionLocal", TestingSessionLocal)
    result = _run(reclassify(args))

    assert result["changed"] >= 1
    refreshed = db.query(PlazaPost).filter(PlazaPost.id == post_id).first()
    assert refreshed.type == "dating"
