"""
日记日期锚定测试
- 测试生成日记的提示词带上真实日期与禁止编造日期的约束
- 测试日记生成 / 补写日记 / AI 点评三个入口都把真实日期传给模型
"""
import asyncio

from fastapi.testclient import TestClient

from app.ai import minimax_client
from app.ai.minimax_client import MiniMaxClient
from app.models.diary import Diary
from tests.conftest import create_test_user, get_auth_header


def _build_client() -> MiniMaxClient:
    return MiniMaxClient(
        api_key="test-key",
        api_base="https://example.com",
        model="test-model",
        mock=False,
    )


class _RecordingClient:
    """记录 generate_diary 入参的假客户端。"""

    def __init__(self):
        self.kwargs = {}

    async def generate_diary(self, materials_text: str, **kwargs):
        self.kwargs = kwargs
        return {
            "title": "测试标题",
            "content": "测试正文",
            "emotion_summary": {"dominant": "平静", "distribution": {"平静": 1.0}},
            "ai_tags": ["测试标签"],
        }


def _capture_diary_prompt(diary_date: str, monkeypatch) -> tuple[str, str]:
    """执行一次 generate_diary，返回 (system_prompt, user_prompt)。"""
    client = _build_client()
    captured = {}

    async def fake_chat_completion(messages, system_prompt="", **_kwargs):
        captured["system"] = system_prompt
        captured["user"] = messages[0]["content"]
        return '{"title": "t", "content": "c", "emotion_summary": {}, "ai_tags": []}'

    monkeypatch.setattr(client, "chat_completion", fake_chat_completion)
    asyncio.run(
        client.generate_diary(
            "[08:00] [文字] 早上去图书馆复习算法",
            weather="晴",
            diary_date=diary_date,
        )
    )
    return captured["system"], captured["user"]


def test_generate_diary_prompt_carries_real_date(monkeypatch):
    """传入日记日期时，提示词必须写明该日期与星期。"""
    system_prompt, user_prompt = _capture_diary_prompt("2026-03-25", monkeypatch)

    assert "- 日记日期：" in user_prompt
    assert "2026年03月25日" in user_prompt
    assert "星期三" in user_prompt
    assert "只能使用该日期" in user_prompt
    assert "严禁编造任何具体年月日、星期、节日或纪念日" in system_prompt


def test_generate_diary_prompt_forbids_date_when_missing(monkeypatch):
    """未提供日期时，提示词必须禁止正文出现任何具体日期。"""
    system_prompt, user_prompt = _capture_diary_prompt("", monkeypatch)

    assert "未提供日记日期" in user_prompt
    assert "严禁在正文出现任何具体年月日、星期或节日" in user_prompt
    assert "只用“今天/早上/傍晚”等相对时间表述" in system_prompt


def test_build_diary_date_context_tolerates_invalid_date():
    """日期格式异常时保留原值，仍然约束只能使用该日期。"""
    context = MiniMaxClient._build_diary_date_context("2026/03/25")

    assert "2026/03/25" in context
    assert "只能使用该日期" in context

    chinese_invalid = MiniMaxClient._build_diary_date_context("不是日期")
    assert "不是日期" in chinese_invalid
    assert "只能使用该日期" in chinese_invalid


def test_build_diary_date_context_empty_or_none():
    """空字符串 / None 必须禁止正文出现任何具体日期。"""
    expected = "未提供日记日期（严禁在正文出现任何具体年月日、星期或节日）"
    assert MiniMaxClient._build_diary_date_context("") == expected
    assert MiniMaxClient._build_diary_date_context(None) == expected  # type: ignore[arg-type]
    assert MiniMaxClient._build_diary_date_context("   ") == expected


def test_build_diary_date_context_iso_datetime_uses_first_ten_chars():
    """带时间后缀的 ISO 串只取前 10 位作为 YYYY-MM-DD。"""
    context = MiniMaxClient._build_diary_date_context("2026-08-19T10:00:00")

    assert "2026年08月19日" in context
    assert "星期三" in context
    assert "只能使用该日期" in context
    assert "T10:00:00" not in context


def test_build_diary_date_context_weekday_mapping():
    """weekday()：0=周一 … 6=周日，映射串为一二三四五六日。"""
    cases = {
        "2026-08-17": "星期一",  # Monday
        "2026-08-18": "星期二",
        "2026-08-19": "星期三",
        "2026-08-20": "星期四",
        "2026-08-21": "星期五",
        "2026-08-22": "星期六",
        "2026-08-16": "星期日",  # Sunday
    }
    for date, weekday in cases.items():
        context = MiniMaxClient._build_diary_date_context(date)
        assert weekday in context, f"{date} 应为 {weekday}，实际：{context}"
        assert "只能使用该日期" in context


def test_generate_diary_api_passes_real_date_to_model(client: TestClient, monkeypatch):
    """日记生成入口必须把日记归属日期传给模型。"""
    auth = create_test_user(client, username="date_ground_gen")
    headers = get_auth_header(auth["token"])

    resp = client.post("/api/materials", json={
        "type": "text",
        "content": "下午在自习室写完了课程设计",
        "date": "2026-03-25",
    }, headers=headers)
    assert resp.status_code == 200

    fake_client = _RecordingClient()
    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake_client)

    gen_resp = client.post("/api/diaries/generate", json={
        "date": "2026-03-25",
        "weather": "晴",
    }, headers=headers)
    assert gen_resp.status_code == 200
    assert fake_client.kwargs.get("diary_date") == "2026-03-25"


def test_backfill_diary_passes_real_date_to_model(client: TestClient, db, monkeypatch):
    """补写日记入口必须把补写日期传给模型。"""
    auth = create_test_user(client, username="date_ground_backfill")
    user_id = auth["user"]["id"]

    from app.ai import service as ai_service
    from app.diary import service as diary_service

    async def fake_understand_images_batch(*_args, **_kwargs):
        return ["窗边的自习室"]

    monkeypatch.setattr(ai_service, "understand_images_batch", fake_understand_images_batch)

    fake_client = _RecordingClient()
    monkeypatch.setattr(minimax_client, "get_minimax_client", lambda: fake_client)

    result = asyncio.run(
        diary_service._create_backfill_diary(
            db,
            user_id,
            "2026-02-14",
            [{"url": "https://example.com/backfill.jpg", "taken_at": 0, "user_note": "自习室"}],
        )
    )

    assert result["date"] == "2026-02-14"
    assert fake_client.kwargs.get("diary_date") == "2026-02-14"


def test_ai_comment_prompt_binds_real_date(db, client: TestClient):
    """AI 点评提示词必须带真实日期，并禁止编造日期。"""
    auth = create_test_user(client, username="date_ground_comment")
    user_id = auth["user"]["id"]

    from app.diary import service as diary_service

    diary = Diary(
        id="diary-date-ground",
        user_id=user_id,
        content="今天在自习室写完了课程设计，心里踏实了不少。",
        title="踏实的一天",
        date="2026-03-25",
        weather="晴",
        emotion_summary="{}",
        created_at=0,
        updated_at=0,
    )

    system_prompt, user_prompt = diary_service._build_ai_comment_prompt_payload(
        db, user_id, diary, []
    )

    assert "- 日期：2026-03-25" in user_prompt
    assert "不得编造具体年月日、星期或节日" in system_prompt
