"""记忆文本归一化与切块。"""
import re


_PARAGRAPH_RE = re.compile(r"\n{3,}")
_SPACE_RE = re.compile(r"[ \t]+")
_LINE_EDGE_SPACE_RE = re.compile(r" *\n *")


def normalize_text(text: str) -> str:
    """清理文本噪音，保留段落结构。"""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    raw = _SPACE_RE.sub(" ", raw)
    raw = _LINE_EDGE_SPACE_RE.sub("\n", raw)
    raw = _PARAGRAPH_RE.sub("\n\n", raw)
    return raw.strip()


def _split_long_piece(piece: str, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(piece):
        end = min(start + chunk_size, len(piece))
        chunk = piece[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(piece):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """按中文友好的段落优先策略切块。"""
    content = normalize_text(text)
    if not content:
        return []
    if len(content) <= chunk_size:
        return [content]

    pieces = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        if len(piece) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_long_piece(piece, chunk_size, overlap))
            continue

        candidate = f"{current}\n\n{piece}".strip() if current else piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = piece

    if current:
        chunks.append(current.strip())

    return [chunk for chunk in chunks if len(chunk.strip()) >= 1]
