import time

from app.models.chat import ChatMessage
from app.models.memory import AvatarCard, MemoryProfile
from app.models.user import User
from app.realtime_voice.config import build_provider_session_config
from app.realtime_voice.prompts import build_realtime_voice_instructions
from tests.conftest import create_test_user


def test_realtime_instructions_follow_structured_voice_guidance():
    prompt = build_realtime_voice_instructions(
        user_name="陈婷婷",
        profile_summary="喜欢校园摄影，社交慢热。",
        boundaries=["不自动申请认识"],
        mode="social_mission",
    )
    for heading in ["# 角色与背景", "# 目标与任务", "# 响应流程", "# 强约束", "# 输出示例", "# 异常处理"]:
        assert heading in prompt
    assert "必须先调用记忆工具" in prompt
    assert "默认单次回复不超过 100 个汉字" in prompt
    assert "AI 可以找人、筛选和试聊，但真人负责判断和承诺" in prompt
    assert "不输出内部思考" in prompt


def test_provider_config_injects_profile_boundaries_and_six_paired_rounds(client, db):
    auth = create_test_user(client, username="voice_prompt")
    user = db.query(User).filter(User.id == auth["user"]["id"]).one()
    now = int(time.time() * 1000)
    db.add(
        MemoryProfile(
            id="profile-voice",
            user_id=user.id,
            profile_type="avatar",
            summary="喜欢晚霞和散步。",
            generated_at=now,
        )
    )
    db.add(
        AvatarCard(
            id="card-voice",
            user_id=user.id,
            boundaries='["不自动发布"]',
            visibility="public",
            updated_at=now,
        )
    )
    for index in range(8):
        db.add(
            ChatMessage(
                id=f"user-{index}",
                user_id=user.id,
                role="user",
                content=f"用户问题 {index}",
                timestamp=now + index * 2,
                session_id=None,
                client_message_id=f"u-{index}",
                attachments="[]",
            )
        )
        db.add(
            ChatMessage(
                id=f"assistant-{index}",
                user_id=user.id,
                role="assistant",
                content=f"助手回答 {index}",
                timestamp=now + index * 2 + 1,
                session_id=None,
                client_message_id=f"a-{index}",
                attachments="[]",
            )
        )
    db.commit()

    config = build_provider_session_config(
        db,
        user=user,
        voice="zh_female_vv_jupiter_bigtts",
        tools=[],
    )
    assert "喜欢晚霞和散步" in config.instructions
    assert "不自动发布" in config.instructions
    assert len(config.initial_context) == 12
    assert config.initial_context[0]["content"][0]["text"] == "用户问题 2"
    assert [item["role"] for item in config.initial_context] == [
        "user",
        "assistant",
    ] * 6
