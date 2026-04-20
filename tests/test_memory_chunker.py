"""记忆切块工具测试。"""

from app.memory.chunker import chunk_text, normalize_text


def test_normalize_text_preserves_paragraphs():
    raw = " 第一段  \r\n\r\n\r\n第二段\t\t内容 \r\n 第三行 "
    normalized = normalize_text(raw)

    assert normalized == "第一段\n\n第二段 内容\n第三行"


def test_chunk_text_returns_single_chunk_for_short_text():
    text = "今天去了图书馆，顺手把想法记下来。"
    chunks = chunk_text(text, chunk_size=100, overlap=10)

    assert chunks == [text]


def test_chunk_text_splits_long_chinese_paragraphs():
    paragraph1 = "今天在图书馆复习离散数学。" * 12
    paragraph2 = "晚上和朋友散步，聊了很多未来的计划。" * 10
    text = f"{paragraph1}\n\n{paragraph2}"

    chunks = chunk_text(text, chunk_size=120, overlap=20)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert any("离散数学" in chunk for chunk in chunks)
    assert any("未来的计划" in chunk for chunk in chunks)


def test_chunk_text_handles_empty_text():
    assert chunk_text("", chunk_size=50, overlap=10) == []
