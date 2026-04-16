"""记忆 prompt 格式化测试。"""

from app.memory.prompts import append_memory_to_system_prompt, format_memory_context


def test_format_memory_context_returns_empty_when_no_memories():
    assert format_memory_context([], scenario="chat") == ""


def test_format_memory_context_truncates_for_avatar_comment():
    memories = [
        {
            "source_type": "diary",
            "title": "周末散步",
            "content": "喜欢傍晚散步。" * 60,
        }
    ]

    context = format_memory_context(memories, scenario="avatar_comment")

    assert "来源：diary / 周末散步" in context
    assert context.endswith("...")
    assert "喜欢傍晚散步。" in context


def test_append_memory_to_system_prompt_adds_social_privacy_notice():
    system_prompt = "你是一个温柔的助手。"
    memory_context = "【相关记忆 1】\n来源：diary / 无标题\n内容：今天很累。"

    merged = append_memory_to_system_prompt(system_prompt, memory_context, scenario="avatar_comment")

    assert system_prompt in merged
    assert "不要泄露私密记忆原文" in merged
    assert memory_context in merged


def test_append_memory_to_system_prompt_returns_original_when_empty():
    system_prompt = "原始 system prompt"

    assert append_memory_to_system_prompt(system_prompt, "", scenario="chat") == system_prompt
