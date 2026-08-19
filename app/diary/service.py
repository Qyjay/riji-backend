"""
日记模块服务层 v2
实现日记 CRUD + AI 生成 + 衍生内容逻辑
"""
import asyncio
from collections import Counter
import json
import os
import re
import time
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.diary import Diary
from app.models.material import RawMaterial
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_ERROR


def _resolve_max_edits_default() -> int:
    """从环境变量读取默认可编辑次数（不依赖 config.py）。"""
    raw = os.getenv("DIARY_MAX_EDITS", "3")
    try:
        value = int(raw)
        return value if value > 0 else 3
    except Exception:
        return 3


DIARY_MAX_EDITS = _resolve_max_edits_default()


def _resolve_derivative_ai_timeout_sec() -> int:
    """读取衍生创作 AI 调用超时时间，避免前端请求先超时。"""
    raw = os.getenv("DERIVATIVE_AI_TIMEOUT_SEC", "60")
    try:
        value = int(raw)
        return value if value > 0 else 8
    except Exception:
        return 8


DERIVATIVE_AI_TIMEOUT_SEC = _resolve_derivative_ai_timeout_sec()
DERIVATIVE_COMIC_FALLBACK_IMAGE = "https://placehold.co/1024x1024/EEE/31343C?text=Diary+Comic&font=roboto"
DERIVATIVE_TASK_TTL_MS = 60 * 60 * 1000
_DERIVATIVE_TASKS: dict[str, dict] = {}
AI_COMMENT_RAG_SOURCE_TYPES = [
    "diary",
    "material",
    "plaza_post",
    "plaza_comment",
    "social_message",
    "chat_session",
]


DEFAULT_EMOTION_EMOJI = {
    "开心": "😊",
    "幸福": "🥰",
    "平静": "😌",
    "感动": "🥹",
    "期待": "🤩",
    "焦虑": "😟",
    "难过": "😢",
    "生气": "😠",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _prune_derivative_tasks(now: Optional[int] = None) -> None:
    current = now or _now_ms()
    expired = [
        task_id
        for task_id, task in _DERIVATIVE_TASKS.items()
        if current - int(task.get("updated_at") or task.get("created_at") or 0) > DERIVATIVE_TASK_TTL_MS
    ]
    for task_id in expired:
        _DERIVATIVE_TASKS.pop(task_id, None)


def _derivative_task_to_dict(task: dict) -> dict:
    return {
        "task_id": task.get("task_id", ""),
        "diary_id": task.get("diary_id", ""),
        "type": task.get("type", ""),
        "status": task.get("status", "running"),
        "derivative_id": task.get("derivative_id") or None,
        "error": task.get("error", ""),
        "created_at": int(task.get("created_at") or 0),
        "updated_at": int(task.get("updated_at") or task.get("created_at") or 0),
    }


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def _decode_dict(s: str) -> dict:
    decoded = _decode(s, {})
    return decoded if isinstance(decoded, dict) else {}


def _apply_material_date_filter(query, date: str):
    """兼容 RawMaterial.date 的按天筛选（YYYY-MM-DD）与精确到秒筛选。"""
    date_value = (date or "").strip()
    if len(date_value) == 10:
        return query.filter(RawMaterial.date.like(f"{date_value}%"))
    return query.filter(RawMaterial.date == date_value)


def _score_to_valence(score_raw, label: str = "") -> int:
    """将情绪分统一为 -10~10 的好坏分，兼容旧版 0~1 / 0~100 置信分。"""
    try:
        score = float(score_raw)
    except Exception:
        score = 0.0

    # 新版分数直接表达情绪好坏；旧版小数/百分制分数需结合情绪类型推断正负。
    if -10 <= score <= 10 and (score < 0 or score > 1 or float(score).is_integer()):
        return max(-10, min(10, int(round(score))))

    if 0 <= score <= 1:
        intensity = score
    elif 1 < score <= 100:
        intensity = score / 100
    else:
        return max(-10, min(10, int(round(score))))

    label_base = {
        "开心": 8,
        "期待": 6,
        "感动": 6,
        "平静": 0,
        "无聊": -2,
        "焦虑": -5,
        "愤怒": -6,
        "难过": -7,
    }.get(label, 0)
    return max(-10, min(10, int(round(label_base * intensity))))


def _build_emotion_trend_from_materials(materials: List[RawMaterial]) -> dict:
    """基于素材列表聚合当日情绪趋势，精确到分钟且同一分钟只保留最早素材。"""
    trend = []
    emotion_counts = {}
    seen_minutes = set()

    def material_ts(material: RawMaterial) -> int:
        return int(material.created_at or material.start_time or material.end_time or 0)

    for m in sorted(materials, key=material_ts):
        em = _decode_dict(m.emotion)
        label = (em.get("label") or "").strip()
        if not label:
            continue

        ts = material_ts(m)
        dt = datetime.fromtimestamp(ts / 1000) if ts else datetime.fromtimestamp(0)
        minute_key = dt.strftime("%H:%M")
        if minute_key in seen_minutes:
            continue
        seen_minutes.add(minute_key)

        score_int = _score_to_valence(em.get("score", 0), label)

        trend.append({
            "hour": dt.hour,
            "minute": dt.minute,
            "time": minute_key,
            "label": label,
            "score": score_int,
        })
        emotion_counts[label] = emotion_counts.get(label, 0) + 1

    dominant = max(emotion_counts, key=emotion_counts.get) if emotion_counts else ""
    return {"dominant": dominant, "trend": trend}


def _build_legacy_emotion_payload(emotion_summary: dict, materials: List[RawMaterial]) -> dict:
    """从情绪趋势构建 legacy emotion 字段，兼容旧端展示。"""
    dominant = (emotion_summary.get("dominant") or "").strip() or "平静"
    trend = emotion_summary.get("trend", [])

    scores = [
        item.get("score", 0)
        for item in trend
        if item.get("label") == dominant
    ]
    if not scores:
        scores = [item.get("score", 0) for item in trend]
    score = int(sum(scores) / len(scores)) if scores else 0

    emoji = ""
    for m in materials:
        em = _decode_dict(m.emotion)
        if em.get("label") == dominant and em.get("emoji"):
            emoji = em.get("emoji")
            break
    if not emoji:
        emoji = DEFAULT_EMOTION_EMOJI.get(dominant, "😐")

    return {
        "emoji": emoji,
        "label": dominant,
        "score": score,
    }


def _format_emotion_trend_for_comment(emotion_summary: dict) -> str:
    """为 AI 点评压缩情绪趋势上下文。"""
    trend = emotion_summary.get("trend", []) if isinstance(emotion_summary, dict) else []
    lines = []
    for item in trend[:24]:
        time_label = str(item.get("time") or "").strip()
        if not time_label:
            try:
                hour = int(item.get("hour", 0))
                minute = int(item.get("minute", 0))
            except Exception:
                hour, minute = 0, 0
            time_label = f"{hour:02d}:{minute:02d}"
        label = str(item.get("label") or "平静").strip()
        score = item.get("score", 0)
        lines.append(f"- {time_label} {label}（好坏分 {score}）")
    return "\n".join(lines) if lines else "- 无有效情绪趋势"


def _build_ai_comment_query(diary: Diary, materials_text: str) -> str:
    """构造记忆检索 query，让 RAG 优先召回与当日主题相关的记忆。"""
    parts = [
        diary.title or "",
        diary.content or "",
        diary.weather or "",
        materials_text or "",
    ]
    return "\n".join(part for part in parts if part).strip()[:1800]


def _build_ai_comment_system_prompt(db: Session, user_id: str, query: str) -> str:
    """使用聊天同源人格，并注入长期记忆/RAG 上下文。"""
    base_prompt = (
        "你是 Avalin 的 AI 伙伴，是用户长期相处并逐渐孵化出的专属数字分身。"
        "你也是用户的 AI 分身，能基于日记和素材给出贴近本人生活脉络的回应。"
        "你了解用户的日记、素材、聊天和长期记忆，负责在每天日记生成后给出一句真实、具体、温暖的点评。\n\n"
        "【角色要求】\n"
        "1. 你不是旁观者，而是熟悉用户生活脉络的 AI 伙伴。\n"
        "2. 可以自然利用相关长期记忆，但不要暴露“我检索到记忆”等系统过程。\n"
        "3. 点评必须贴合当天日记内容，关注用户的感受、成长、关系或选择。\n"
        "4. 语气克制、亲近、真诚，不说教，不夸张治愈，不给空泛鸡汤。\n"
        "5. 不虚构日记没有出现的事实，不做医学、心理诊断。\n"
        "6. 不得编造具体年月日、星期或节日；如需提及日期，只能使用上下文给出的日记日期。\n\n"
        "【输出要求】\n"
        "只输出一句中文点评，20 到 60 字；不要 JSON；不要引号；不要 Markdown；不要换行。"
    )
    if not getattr(settings, "MEMORY_ENABLED", True):
        return base_prompt
    try:
        from app.memory.prompts import append_memory_to_system_prompt, format_memory_context
        from app.memory.retriever import retrieve_memories

        memories = retrieve_memories(
            db,
            user_id=user_id,
            query=query,
            scenario="chat",
            top_k=getattr(settings, "MEMORY_TOP_K", 6),
            source_types=AI_COMMENT_RAG_SOURCE_TYPES,
        )
        memory_context = format_memory_context(memories, scenario="chat")
        return append_memory_to_system_prompt(base_prompt, memory_context, scenario="chat")
    except Exception:
        return base_prompt


def _sanitize_ai_comment(raw: str) -> str:
    """规范模型输出，避免多余格式污染页面。"""
    text_value = re.sub(r"\s+", " ", str(raw or "").strip())
    text_value = re.sub(r"^```(?:\w+)?|```$", "", text_value).strip()
    text_value = text_value.strip("\"'“”‘’")
    if len(text_value) > 80:
        text_value = text_value[:80].rstrip("，。,. ") + "..."
    return text_value


def _build_ai_comment_prompt_payload(
    db: Session,
    user_id: str,
    diary: Diary,
    materials: List[RawMaterial],
    materials_text: str = "",
) -> tuple[str, str]:
    """构造日记 AI 点评的 system/user prompt。"""
    material_context = materials_text or _build_materials_prompt_text(materials, diary.date or "")
    emotion_summary = _decode_dict(diary.emotion_summary)
    query = _build_ai_comment_query(diary, material_context)
    system_prompt = _build_ai_comment_system_prompt(db, user_id, query)
    user_prompt = (
        "请为下面这篇日记写一句 AI 分身点评。\n\n"
        f"- 日期：{diary.date or '未提供（不要提及任何具体日期）'}\n"
        f"- 标题：{diary.title or '无标题'}\n"
        f"- 天气：{diary.weather or '未记录'}\n"
        f"- 主要情绪：{emotion_summary.get('dominant') or '未识别'}\n"
        "- 情绪趋势：\n"
        f"{_format_emotion_trend_for_comment(emotion_summary)}\n\n"
        "- 当日素材摘要：\n"
        f"{material_context[:1800] or '无'}\n\n"
        "- 日记正文：\n"
        f"{(diary.content or '')[:2600]}"
    )
    return system_prompt, user_prompt


def _sse_event(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _format_material_time(m: RawMaterial) -> str:
    """为素材生成统一时间标签（HH:MM 或 HH:MM~HH:MM）。"""
    if m.type == "chat" and m.start_time and m.end_time:
        s = datetime.fromtimestamp(m.start_time / 1000).strftime("%H:%M")
        e = datetime.fromtimestamp(m.end_time / 1000).strftime("%H:%M")
        return f"{s}~{e}"

    ts = m.created_at or m.start_time or m.end_time
    if ts:
        return datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
    return "未知时间"


def _normalize_chat_material_content(content: str) -> str:
    """将 chat 素材内容归一到用户第一人称，便于日记叙事融合。"""
    normalized_content = re.sub(r"\s+", " ", str(content or "").strip())
    if not normalized_content:
        return ""

    replacements = [
        ("用户和AI", "我和AI"),
        ("用户与AI", "我和AI"),
        ("用户跟AI", "我和AI"),
        ("用户同AI", "我和AI"),
        ("用户和 AI", "我和AI"),
        ("用户与 AI", "我和AI"),
        ("用户跟 AI", "我和AI"),
        ("用户同 AI", "我和AI"),
        ("用户：", "我："),
        ("用户:", "我:"),
    ]
    for old, new in replacements:
        normalized_content = normalized_content.replace(old, new)

    return normalized_content


def _build_materials_prompt_text(
    materials: List[RawMaterial],
    date: str,
    image_hints: dict = None,
) -> str:
    """将素材整理为按时间排序的提示词上下文文本。"""
    if not materials:
        return f"今天是 {date}，无具体素材记录。"

    parts = []
    for m in materials:
        time_label = _format_material_time(m)
        if m.type == "text" and m.content:
            parts.append(f"[{time_label}] [文字] {m.content}")
        elif m.type == "image":
            image_desc = (m.content or "").strip()
            if image_hints:
                material_hints = image_hints.get(m.id) or []
                if isinstance(material_hints, str):
                    material_hints = [material_hints]

                cleaned_hints = [
                    str(hint or "").strip()
                    for hint in material_hints
                    if str(hint or "").strip()
                ]
                if cleaned_hints:
                    hint_text = "；".join(cleaned_hints)
                    if image_desc and hint_text not in image_desc:
                        image_desc = f"{image_desc}；AI识图补充：{hint_text}"
                    elif not image_desc:
                        image_desc = hint_text
            if image_desc:
                parts.append(f"[{time_label}] [图片描述] {image_desc}")
        elif m.type == "voice" and m.content:
            parts.append(f"[{time_label}] [语音转文字] {m.content}")
        elif m.type == "chat" and m.content:
            chat_content = _normalize_chat_material_content(m.content)
            if not chat_content:
                continue
            time_range = ""
            if m.start_time and m.end_time:
                s = datetime.fromtimestamp(m.start_time / 1000).strftime("%H:%M")
                e = datetime.fromtimestamp(m.end_time / 1000).strftime("%H:%M")
                time_range = f"({s}~{e}) "
            parts.append(f"[对话记录] {time_range}{chat_content}")

    return "\n".join(parts) if parts else f"今天是 {date}，无具体素材记录。"


def _extract_material_media_urls(m: RawMaterial) -> List[str]:
    """兼容旧 string 与新 JSON 数组格式的素材媒体 URL。"""
    decoded = _decode(m.media_url or "", None)
    if isinstance(decoded, str):
        raw_items = [decoded]
    elif isinstance(decoded, list):
        raw_items = decoded
    else:
        raw_items = [m.media_url or ""]

    urls: List[str] = []
    for item in raw_items:
        url = ""
        if isinstance(item, str):
            url = item.strip()
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()

        if url and url not in urls:
            urls.append(url)
    return urls


def _collect_today_image_urls(materials: List[RawMaterial]) -> List[str]:
    """提取当日图片素材 URL，按时间顺序去重。"""
    urls = []
    seen = set()
    for m in materials:
        if m.type != "image":
            continue
        for url in _extract_material_media_urls(m):
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


async def _collect_image_understand_hints(materials: List[RawMaterial]) -> dict:
    """提取图片视觉理解结果：按图片数量逐张返回。"""
    image_entries: List[tuple[str, str]] = []
    for material in materials:
        if material.type != "image":
            continue
        for image_url in _extract_material_media_urls(material):
            image_entries.append((material.id, image_url))

    if not image_entries:
        return {}

    from app.ai import service as ai_service

    results = await ai_service.understand_images_batch(
        image_urls=[item[1] for item in image_entries],
        prompt=str(
            getattr(settings, "VIVO_VISION_PROMPT", "")
            or getattr(settings, "ARK_VISION_PROMPT", "")
            or ""
        ),
        timeout_sec=int(
            getattr(settings, "VIVO_VISION_TIMEOUT_SEC", 0)
            or getattr(settings, "ARK_VISION_TIMEOUT_SEC", 50)
            or 50
        ),
        max_images=len(image_entries),
    )

    hints: dict = {}
    for idx, (material_id, _image_url) in enumerate(image_entries):
        description = ""
        if idx < len(results):
            description = str(results[idx] or "").strip()
        if not description:
            continue
        hints.setdefault(material_id, []).append(description)

    return hints


def _build_image_understanding_list(materials: List[RawMaterial], image_hints: dict) -> List[str]:
    """按素材顺序汇总图片理解内容（按图片逐条保留）。"""
    if not image_hints:
        return []

    items: List[str] = []
    for m in materials:
        if m.type != "image":
            continue
        material_hints = image_hints.get(m.id) or []
        if isinstance(material_hints, str):
            material_hints = [material_hints]
        for hint in material_hints:
            hint_text = str(hint or "").strip()
            if hint_text:
                items.append(hint_text)
    return items


def _collect_today_material_tags(materials: List[RawMaterial]) -> List[str]:
    """汇总当日素材标签，按出现顺序去重。"""
    tags = []
    seen = set()
    for m in materials:
        raw_tags = _decode(m.tags, [])
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        if not isinstance(raw_tags, list):
            continue

        for tag in raw_tags:
            tag_text = str(tag or "").strip()
            if not tag_text or tag_text in seen:
                continue
            seen.add(tag_text)
            tags.append(tag_text)
    return tags


def _fallback_ai_tags(weather: str, emotion_summary: dict) -> List[str]:
    """当 AI 未返回标签时的兜底标签（保证 2-3 个）。"""
    candidates = []

    weather_text = (weather or "").strip()
    if weather_text:
        weather_tag = weather_text.split(" ")[0][:8]
        if weather_tag:
            candidates.append(weather_tag)

    dominant = (emotion_summary.get("dominant") or "").strip()
    if dominant:
        candidates.append(f"{dominant}心情")

    candidates.extend(["日常记录", "生活片段", "今日随记", "心情日记"])

    result = []
    for tag in candidates:
        if tag not in result:
            result.append(tag)
        if len(result) >= 3:
            break

    return result[:3] if len(result) >= 2 else ["日常记录", "生活片段"]


def _extract_ai_tags(result: dict, weather: str, emotion_summary: dict) -> List[str]:
    """从 AI 结果提取 2-3 个标签，不足时补齐。"""
    raw_tags = result.get("ai_tags", []) if isinstance(result, dict) else []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if not isinstance(raw_tags, list):
        raw_tags = []

    normalized = []
    for tag in raw_tags:
        tag_text = str(tag or "").strip()
        if not tag_text:
            continue
        if tag_text in normalized:
            continue
        normalized.append(tag_text)
        if len(normalized) >= 3:
            break

    if len(normalized) < 2:
        fallback = _fallback_ai_tags(weather, emotion_summary)
        for tag in fallback:
            if tag not in normalized:
                normalized.append(tag)
            if len(normalized) >= 3:
                break

    return normalized[:3]


def _merge_diary_tags(material_tags: List[str], ai_tags: List[str]) -> List[str]:
    """合并素材标签与 AI 标签，保持顺序并去重。"""
    merged = []
    for tag in material_tags + ai_tags:
        tag_text = str(tag or "").strip()
        if not tag_text or tag_text in merged:
            continue
        merged.append(tag_text)
    return merged


def _build_derivative_text_fallback(
    dtype: str,
    diary_excerpt: str,
    weather_ctx: str,
    emotion_ctx: str,
) -> str:
    """衍生创作兜底文案：当 AI 超时/失败时返回可读结果。"""
    snippet = re.sub(r"\s+", " ", str(diary_excerpt or "").strip())
    if not snippet:
        snippet = "今天我记录了一些日常片段，也重新整理了自己的想法。"

    if dtype == "novel":
        return (
            f"{weather_ctx}的这一天，我的情绪更偏向{emotion_ctx}。"
            f"回头看这些经历，{snippet[:140]}。"
            "当我把这些瞬间串起来时，才发现那些看似平常的细节，"
            "其实都在悄悄塑造现在的我。"
        )

    # share_card
    return f"{weather_ctx}的一天里，我带着{emotion_ctx}走过这些片段：{snippet[:48]}。"


def _parse_csv_values(raw: str) -> List[str]:
    """解析逗号分隔参数，返回去重后的非空列表。"""
    if not raw:
        return []
    items = [part.strip() for part in str(raw).split(",")]
    result = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _normalize_weather_text(weather: str) -> str:
    """规范化天气文本：去除温度，仅保留天气描述。"""
    raw = str(weather or "").strip()
    if not raw:
        return ""

    normalized = re.sub(
        r"(?:气温|温度|体感|最高|最低)?\s*[-+]?\d+(?:\.\d+)?\s*(?:°\s*[cC]|℃|摄氏度|度)",
        "",
        raw,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,，;；/|")
    return normalized or raw


def _normalize_weather_periods(periods: Optional[List[dict]]) -> List[dict]:
    if not isinstance(periods, list):
        return []

    allowed = {
        "morning": "上午",
        "afternoon": "下午",
        "evening": "晚上",
    }
    result = []
    for item in periods:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key not in allowed:
            continue
        weather_text = str(item.get("weatherText") or item.get("weather") or "").strip()
        if not weather_text:
            continue
        result.append({
            "key": key,
            "label": str(item.get("label") or allowed[key]).strip() or allowed[key],
            "weatherText": weather_text,
        })
    return result


def _weather_from_periods(periods: List[dict]) -> str:
    parts = [
        f"{item['label']}{item['weatherText']}"
        for item in periods
        if item.get("label") and item.get("weatherText")
    ]
    return "；".join(parts)


def _parse_weather_values(raw: str) -> List[str]:
    """解析并规范化 weather 参数，支持逗号分隔。"""
    values = _parse_csv_values(raw)
    result = []
    for value in values:
        normalized = _normalize_weather_text(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _sqlite_json_available(db: Session) -> bool:
    """检查当前 SQLite 是否支持 JSON 函数。"""
    try:
        db.execute(text("SELECT json_extract('{\"a\":\"b\"}', '$.a')"))
        return True
    except Exception:
        return False


def _apply_sqlite_tag_filter(query, tags: List[str]):
    """使用 SQLite json_each 做 tags 交集过滤（同维度 OR）。"""
    placeholders = []
    params = {}
    for idx, tag in enumerate(tags):
        key = f"tag_{idx}"
        placeholders.append(f":{key}")
        params[key] = tag

    condition = text(
        "EXISTS ("
        "SELECT 1 FROM json_each(diaries.tags) "
        f"WHERE json_each.value IN ({', '.join(placeholders)})"
        ")"
    )
    return query.filter(condition).params(**params)


def _matches_any_tag(diary: Diary, expected_tags: List[str]) -> bool:
    """Python 层 tags OR 匹配（SQLite JSON 不可用时回退）。"""
    diary_tags = _decode(diary.tags, [])
    if isinstance(diary_tags, str):
        diary_tags = [diary_tags]
    if not isinstance(diary_tags, list):
        return False

    tag_set = {str(tag).strip() for tag in diary_tags if str(tag).strip()}
    return any(tag in tag_set for tag in expected_tags)


def diary_to_dict(d: Diary) -> dict:
    """日记模型转响应字典（全字段，camelCase 由 schema 处理）"""
    emotion_summary = _decode_dict(d.emotion_summary)
    # 从 emotion_summary 提取 legacy emotion 字段
    dominant = emotion_summary.get("dominant", "")
    trend = emotion_summary.get("trend", [])
    legacy_score = trend[0]["score"] if trend else 0
    emotion = _decode(d.emotion, {
        "emoji": "😐",
        "label": dominant or "平静",
        "score": legacy_score,
    })
    if not isinstance(emotion, dict):
        emotion = {
            "emoji": "😐",
            "label": dominant or "平静",
            "score": legacy_score,
        }
    if dominant and not emotion.get("label"):
        emotion["label"] = dominant

    return {
        "id": d.id,
        "user_id": d.user_id,
        "title": d.title or "",
        "content": d.content or "",
        "date": d.date or "",
        "weather": d.weather or "",
        "special_date": d.special_date or "",
        "ai_comment": d.ai_comment or "",
        "emotion_summary": emotion_summary,
        "material_ids": _decode(d.material_ids, []),
        "style": d.style or "日记式",
        "edit_count": d.edit_count or 0,
        "max_edits": d.max_edits if (d.max_edits and d.max_edits > 0) else DIARY_MAX_EDITS,
        "status": d.status or "draft",
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        # legacy 兼容
        "emotion": emotion,
        "images": _decode(d.images, []),
        "image_understandings": _decode(d.image_understandings, []),
        "tags": _decode(d.tags, []),
        "location": d.location or "",
        "has_comic": d.has_comic or False,
        "has_bgm": d.has_bgm or False,
    }


def _diary_response(d: Diary) -> dict:
    """Serialize a diary with the API's camelCase response contract."""
    from app.diary.schemas import DiaryOut

    return DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True)


async def _generate_ai_comment_for_diary(
    db: Session,
    user_id: str,
    diary: Diary,
    materials: List[RawMaterial],
    materials_text: str = "",
) -> str:
    """调用聊天同源 LLM + RAG，为日记生成真实 AI 分身点评。"""
    from app.ai.minimax_client import get_minimax_client

    client = get_minimax_client()
    if not hasattr(client, "generate_diary_comment"):
        return ""

    system_prompt, user_prompt = _build_ai_comment_prompt_payload(
        db,
        user_id,
        diary,
        materials,
        materials_text=materials_text,
    )
    try:
        comment = await client.generate_diary_comment(
            user_prompt,
            system_prompt=system_prompt,
        )
        return _sanitize_ai_comment(comment)
    except Exception:
        return ""


async def generate_diary_ai_comment(db: Session, user_id: str, diary_id: str) -> dict:
    """为已有日记生成并持久化 AI 分身点评，幂等避免重复调用模型。"""
    diary = (
        db.query(Diary)
        .filter(Diary.id == diary_id, Diary.user_id == user_id)
        .first()
    )
    if not diary:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    if (diary.ai_comment or "").strip():
        return {"aiComment": diary.ai_comment or ""}

    material_ids = _decode(diary.material_ids, [])
    materials = []
    if material_ids:
        materials = (
            db.query(RawMaterial)
            .filter(RawMaterial.user_id == user_id, RawMaterial.id.in_(material_ids))
            .order_by(RawMaterial.created_at)
            .all()
        )

    comment = await _generate_ai_comment_for_diary(db, user_id, diary, materials)
    if not comment:
        raise ApiException(code=PARAM_ERROR, message="AI 点评生成失败，请稍后重试", status_code=500)

    diary.ai_comment = comment
    diary.updated_at = _now_ms()
    db.commit()
    db.refresh(diary)
    return {"aiComment": diary.ai_comment or ""}


async def stream_diary_ai_comment(user_id: str, diary_id: str, bind=None):
    """流式生成 AI 点评，结束后将完整内容保存到 diaries.ai_comment。"""
    from app.ai.minimax_client import get_minimax_client
    from app.database import SessionLocal

    yield _sse_event({"type": "start"})
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=bind) if bind is not None else SessionLocal
    db = session_factory()
    full_reply = ""
    try:
        diary = (
            db.query(Diary)
            .filter(Diary.id == diary_id, Diary.user_id == user_id)
            .first()
        )
        if not diary:
            yield _sse_event({"type": "error", "message": "日记不存在"})
            return

        if (diary.ai_comment or "").strip():
            full_reply = _sanitize_ai_comment(diary.ai_comment or "")
            yield _sse_event({"type": "chunk", "text": full_reply})
            yield _sse_event({"type": "done", "aiComment": full_reply})
            return

        material_ids = _decode(diary.material_ids, [])
        materials = []
        if material_ids:
            materials = (
                db.query(RawMaterial)
                .filter(RawMaterial.user_id == user_id, RawMaterial.id.in_(material_ids))
                .order_by(RawMaterial.created_at)
                .all()
            )

        system_prompt, user_prompt = _build_ai_comment_prompt_payload(
            db,
            user_id,
            diary,
            materials,
        )
        client = get_minimax_client()
        messages = [{"role": "user", "content": user_prompt}]

        try:
            async for chunk in client.stream_chat(messages, system_prompt=system_prompt):
                if not chunk:
                    continue
                full_reply += chunk
                yield _sse_event({"type": "chunk", "text": chunk})
        except Exception:
            fallback_reply = await client.generate_diary_comment(
                user_prompt,
                system_prompt=system_prompt,
            )
            full_reply = fallback_reply or ""
            if full_reply:
                yield _sse_event({"type": "chunk", "text": full_reply})

        comment = _sanitize_ai_comment(full_reply)
        if not comment:
            yield _sse_event({"type": "error", "message": "AI 点评生成失败，请稍后重试"})
            return

        diary.ai_comment = comment
        diary.updated_at = _now_ms()
        db.commit()
        yield _sse_event({"type": "done", "aiComment": comment})
    except Exception as exc:
        db.rollback()
        yield _sse_event({"type": "error", "message": str(exc)})
    finally:
        db.close()


def list_diaries(db: Session, user_id: str, page: int = 1, page_size: int = 10) -> dict:
    """分页查询日记列表"""
    total = db.query(Diary).filter(Diary.user_id == user_id).count()
    offset = (page - 1) * page_size
    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user_id)
        .order_by(Diary.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    from app.diary.schemas import DiaryOut
    items = [DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True) for d in diaries]
    return {"items": items, "total": total}


def search_diaries(db: Session, user_id: str, params) -> dict:
    """搜索日记：多条件 AND，同维度 OR。"""
    q = (params.q or "").strip()
    emotion_list = _parse_csv_values(params.emotion)
    tag_list = _parse_csv_values(params.tag)
    weather_list = _parse_weather_values(params.weather)
    from_date = (params.from_date or "").strip()
    to_date = (params.to_date or "").strip()

    query = db.query(Diary).filter(Diary.user_id == user_id)

    if q:
        like_q = f"%{q}%"
        query = query.filter(
            or_(
                Diary.title.ilike(like_q),
                Diary.content.ilike(like_q),
                Diary.location.ilike(like_q),
            )
        )

    if emotion_list:
        query = query.filter(
            func.json_extract(Diary.emotion_summary, "$.dominant").in_(emotion_list)
        )

    if weather_list:
        weather_conditions = []
        for weather_item in weather_list:
            weather_conditions.append(Diary.weather == weather_item)
            weather_conditions.append(Diary.weather.ilike(f"{weather_item}%"))
        query = query.filter(or_(*weather_conditions))

    if from_date:
        query = query.filter(Diary.date >= from_date)
    if to_date:
        query = query.filter(Diary.date <= to_date)

    page = max(1, int(params.page or 1))
    page_size = max(1, int(params.page_size or 20))
    offset = (page - 1) * page_size

    ordered_query = query.order_by(Diary.created_at.desc())

    diaries = []
    total = 0
    if tag_list:
        used_sqlite_json = False

        if _sqlite_json_available(db):
            try:
                tagged_query = _apply_sqlite_tag_filter(ordered_query, tag_list)
                total = tagged_query.count()
                diaries = tagged_query.offset(offset).limit(page_size).all()
                used_sqlite_json = True
            except Exception:
                used_sqlite_json = False

        if not used_sqlite_json:
            filtered = [d for d in ordered_query.all() if _matches_any_tag(d, tag_list)]
            total = len(filtered)
            diaries = filtered[offset:offset + page_size]
    else:
        total = ordered_query.count()
        diaries = ordered_query.offset(offset).limit(page_size).all()

    from app.diary.schemas import DiaryOut

    items = [DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True) for d in diaries]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_diary(db: Session, user_id: str, diary_id: str) -> dict:
    """获取单篇日记"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)
    from app.diary.schemas import DiaryOut
    return DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True)


def update_diary(db: Session, user_id: str, diary_id: str, data: dict) -> dict:
    """更新日记（检查修改次数限制）"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    current_max_edits = d.max_edits if (d.max_edits and d.max_edits > 0) else DIARY_MAX_EDITS
    if (d.edit_count or 0) >= current_max_edits:
        raise ApiException(
            code=PARAM_ERROR,
            message=f"日记最多只能修改 {current_max_edits} 次，已达上限",
            status_code=400,
        )

    if "content" in data and data["content"] is not None:
        d.content = data["content"]

    d.edit_count = (d.edit_count or 0) + 1
    d.updated_at = _now_ms()
    db.commit()
    db.refresh(d)
    from app.memory.ingestion import ingest_diary

    ingest_diary(db, d)
    from app.diary.schemas import DiaryOut
    return DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True)


async def generate_diary(
    db: Session,
    user_id: str,
    date: str,
    weather: str = "",
    weather_periods: Optional[List[dict]] = None,
    allow_fallback: bool = False,
) -> dict:
    """AI 生成当日日记"""
    normalized_weather_periods = _normalize_weather_periods(weather_periods)
    normalized_weather = _weather_from_periods(normalized_weather_periods) or _normalize_weather_text(weather)

    existing = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .first()
    )
    if existing:
        return _diary_response(existing)

    materials_query = db.query(RawMaterial).filter(RawMaterial.user_id == user_id)
    materials = (
        _apply_material_date_filter(materials_query, date)
        .order_by(RawMaterial.created_at)
        .all()
    )

    if not materials and not allow_fallback:
        raise ApiException(
            code=PARAM_ERROR,
            message="请先记录今天的素材",
            status_code=400,
        )

    emotion_summary_for_prompt = _build_emotion_trend_from_materials(materials)
    if normalized_weather_periods:
        emotion_summary_for_prompt["weatherPeriods"] = normalized_weather_periods

    user = db.query(User).filter(User.id == user_id).first()
    user_style = ""
    if user and user.style_tags:
        try:
            tags = json.loads(user.style_tags)
            user_style = "、".join(tags) if tags else ""
        except Exception:
            pass

    image_hints = await _collect_image_understand_hints(materials)
    image_understandings = _build_image_understanding_list(materials, image_hints)
    materials_text = _build_materials_prompt_text(materials, date, image_hints=image_hints)

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.generate_diary(
        materials_text,
        weather=normalized_weather,
        user_style=user_style,
        daily_emotion_summary=emotion_summary_for_prompt,
        diary_date=date,
    )

    now = _now_ms()
    material_ids = [m.id for m in materials]
    emotion_summary = emotion_summary_for_prompt
    emotion_payload = _build_legacy_emotion_payload(emotion_summary, materials)
    diary_images = _collect_today_image_urls(materials)
    material_tags = _collect_today_material_tags(materials)
    ai_tags = _extract_ai_tags(result, normalized_weather, emotion_summary)
    diary_tags = _merge_diary_tags(material_tags, ai_tags)

    # AI 调用耗时较长，并发请求可能同时进入；写入前必须再次检查。
    existing = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .first()
    )

    if existing:
        return _diary_response(existing)

    d = Diary(
        id=_uuid(),
        user_id=user_id,
        content=result.get("content", ""),
        title=result.get("title", "今日日记"),
        images=_encode(diary_images),
        image_understandings=_encode(image_understandings),
        emotion=_encode(emotion_payload),
        tags=_encode(diary_tags),
        weather=normalized_weather,
        date=date,
        material_ids=_encode(material_ids),
        emotion_summary=_encode(emotion_summary),
        status="draft",
        edit_count=0,
        max_edits=DIARY_MAX_EDITS,
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    if user:
        user.diary_count = (user.diary_count or 0) + 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Diary)
            .filter(Diary.user_id == user_id, Diary.date == date)
            .first()
        )
        if existing:
            return _diary_response(existing)
        raise

    # 通过“当日情绪趋势”逻辑再次聚合，作为最终 emotion/emotion_summary。
    trend_summary = get_emotion_trend(db, user_id, d.id)
    if normalized_weather_periods:
        trend_summary["weatherPeriods"] = normalized_weather_periods
    d.emotion_summary = _encode(trend_summary)
    d.emotion = _encode(_build_legacy_emotion_payload(trend_summary, materials))
    d.updated_at = _now_ms()
    db.commit()

    db.refresh(d)
    ai_comment = await _generate_ai_comment_for_diary(
        db,
        user_id,
        d,
        materials,
        materials_text=materials_text,
    )
    if ai_comment:
        d.ai_comment = ai_comment
        d.updated_at = _now_ms()
        db.commit()
        db.refresh(d)

    from app.memory.ingestion import ingest_diary

    ingest_diary(db, d)
    return _diary_response(d)


def _list_material_user_ids_by_date(db: Session, date: str) -> List[str]:
    """查询指定日期存在素材的用户 ID（去重）。"""
    rows = (
        _apply_material_date_filter(
            db.query(RawMaterial.user_id),
            date,
        )
        .distinct()
        .all()
    )

    user_ids: List[str] = []
    for row in rows:
        user_id = str(row[0]).strip() if row and row[0] is not None else ""
        if user_id:
            user_ids.append(user_id)
    return user_ids


async def auto_generate_missing_diaries(
    db: Session,
    date: str,
    weather: str = "",
) -> dict:
    """为指定日期自动补生成日记（仅补未生成用户）。"""
    candidate_user_ids = _list_material_user_ids_by_date(db, date)
    generated = 0
    skipped_existing = 0
    failed = []

    for user_id in candidate_user_ids:
        has_diary = db.query(Diary.id).filter(
            Diary.user_id == user_id,
            Diary.date == date,
        ).first()
        if has_diary:
            skipped_existing += 1
            continue

        try:
            await generate_diary(
                db=db,
                user_id=user_id,
                date=date,
                weather=weather,
                allow_fallback=False,
            )
            generated += 1
        except ApiException as exc:
            db.rollback()
            failed.append({"user_id": user_id, "reason": exc.message})
        except Exception as exc:
            db.rollback()
            failed.append({"user_id": user_id, "reason": str(exc)})

    return {
        "date": date,
        "candidate_count": len(candidate_user_ids),
        "generated_count": generated,
        "skipped_existing_count": skipped_existing,
        "failed": failed,
    }


def get_emotion_trend(db: Session, user_id: str, diary_id: str) -> dict:
    """从关联素材聚合情绪趋势"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    saved_summary = _decode(d.emotion_summary, {})
    weather_periods = saved_summary.get("weatherPeriods") if isinstance(saved_summary, dict) else []
    if not isinstance(weather_periods, list):
        weather_periods = []

    material_ids = _decode(d.material_ids, [])
    if not material_ids:
        result = {"dominant": "", "trend": []}
        if weather_periods:
            result["weatherPeriods"] = weather_periods
        return result

    materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.id.in_(material_ids))
        .order_by(RawMaterial.created_at)
        .all()
    )
    result = _build_emotion_trend_from_materials(materials)
    if weather_periods:
        result["weatherPeriods"] = weather_periods
    return result


async def extract_diary_info(db: Session, user_id: str, diary_id: str) -> dict:
    """AI 提取纪念日/人物/偏好"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.extract_info(d.content)

    now = _now_ms()

    # 写入纪念日
    anniversaries_out = []
    from app.models.anniversary import Anniversary
    seen_ann_keys = set()
    for item in result.get("anniversaries", []):
        if item.get("title") and item.get("date"):
            title = item["title"]
            ann_date = item["date"]
            related_person = item.get("relatedPerson", item.get("related_person", ""))
            ann_key = (title, ann_date, related_person)
            if ann_key in seen_ann_keys:
                continue
            seen_ann_keys.add(ann_key)

            existing_ann = (
                db.query(Anniversary)
                .filter(
                    Anniversary.user_id == user_id,
                    Anniversary.diary_id == diary_id,
                    Anniversary.title == title,
                    Anniversary.date == ann_date,
                    Anniversary.related_person == related_person,
                )
                .first()
            )

            if not existing_ann:
                ann = Anniversary(
                    id=_uuid(),
                    user_id=user_id,
                    title=title,
                    date=ann_date,
                    source="ai_extracted",
                    related_person=related_person,
                    diary_id=diary_id,
                    created_at=now,
                )
                db.add(ann)

            anniversaries_out.append({
                "title": title,
                "date": ann_date,
                "relatedPerson": related_person,
            })

    # 更新用户画像
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(id=_uuid(), user_id=user_id, updated_at=now)
        db.add(profile)

    existing_relations = _decode(profile.relations, {})
    for person in result.get("persons", []):
        if person.get("name"):
            existing_relations[person["name"]] = person.get("relation", "")
    profile.relations = _encode(existing_relations)

    existing_interests = _decode(profile.interests, [])
    new_prefs = []
    for p in result.get("preferences", []):
        if isinstance(p, str) and p:
            new_prefs.append(p)
        elif isinstance(p, dict) and p.get("item"):
            new_prefs.append(p["item"])
    merged = list(set(existing_interests + new_prefs))
    profile.interests = _encode(merged)
    profile.updated_at = now

    db.commit()

    # Build response
    relations_out = [
        {"name": p["name"], "relation": p.get("relation", ""), "mentions": p.get("mentions", 1)}
        for p in result.get("persons", [])
        if p.get("name")
    ]
    preferences_out = result.get("preferences", [])

    return {
        "anniversaries": anniversaries_out,
        "persons": relations_out,
        "relations": relations_out,
        "preferences": preferences_out,
    }


async def generate_derivative(db: Session, user_id: str, diary_id: str, dtype: str) -> dict:
    """生成衍生内容（漫画/小说/分享卡）"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    # 兼容前端预览页兜底 diaryId='1' 的历史写法：回退到用户最近一篇日记。
    if not d and str(diary_id).strip() == "1":
        d = (
            db.query(Diary)
            .filter(Diary.user_id == user_id)
            .order_by(Diary.created_at.desc())
            .first()
        )
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    target_diary_id = d.id

    allowed_types = {"comic", "novel", "share_card"}
    if dtype not in allowed_types:
        raise ApiException(
            code=PARAM_ERROR,
            message=f"不支持的衍生类型: {dtype}，仅支持 comic/novel/share_card",
            status_code=400,
        )

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    content = ""
    media_url = ""
    now = _now_ms()

    emotion_ctx = _decode_dict(d.emotion_summary).get("dominant", "") or "平静"
    weather_ctx = d.weather or "未记录天气"
    diary_excerpt = (d.content or "").strip()

    if dtype == "comic":
        prompt = (
            "请根据以下日记生成一张“多格剧情漫画”图（单张图片内包含 4~6 格分镜），画风稳定为："
            "治愈系青春日常、手绘线稿、柔和暖色、构图干净、真实生活感。\n"
            "必须要求：\n"
            "1. 必须是多格漫画（至少四格），并按时间顺序推进剧情：开场-发展-转折-收束。\n"
            "2. 每一格都要有明确场景变化与动作，不可做成同一画面的重复切片。\n"
            "3. 画面内容严格基于日记事实，不夸张魔幻、不科幻。\n"
            "4. 强化当日主要情绪与氛围，让情绪随剧情有起伏。\n"
            "5. 不要出现文字、对白框、Logo、水印、边框、拼贴。\n"
            "6. 人物比例自然，场景细节清晰。\n"
            f"天气：{weather_ctx}；主要情绪：{emotion_ctx}。\n"
            f"日记内容：{diary_excerpt[:500]}"
        )
        try:
            media_url = await asyncio.wait_for(
                client.generate_image(prompt, aspect_ratio="1:1"),
                timeout=DERIVATIVE_AI_TIMEOUT_SEC,
            )
        except Exception:
            media_url = DERIVATIVE_COMIC_FALLBACK_IMAGE
        if not media_url:
            media_url = DERIVATIVE_COMIC_FALLBACK_IMAGE
    elif dtype == "novel":
        system_prompt = (
            "你是短篇小说改写编辑。"
            "请将日记改写为风格稳定的现实向青春短篇，保留原始事件顺序与核心细节，"
            "增强叙事张力与场景描写，但不得虚构关键事实。"
            "输出要求：\n"
            "1. 第一人称中文叙述；\n"
            "2. 350-600 字；\n"
            "3. 单篇连贯正文，不分章节，不加小标题；\n"
            "4. 融入天气与情绪变化；\n"
            "5. 仅输出正文。"
        )
        user_prompt = (
            f"请将下面日记改写为短篇小说。天气：{weather_ctx}；主要情绪：{emotion_ctx}。\n\n"
            f"原始日记：\n{diary_excerpt}"
        )
        messages = [{"role": "user", "content": user_prompt}]
        try:
            content = await asyncio.wait_for(
                client.chat_completion(messages, system_prompt=system_prompt, temperature=0.65),
                timeout=DERIVATIVE_AI_TIMEOUT_SEC,
            )
        except Exception:
            content = _build_derivative_text_fallback(
                dtype="novel",
                diary_excerpt=diary_excerpt,
                weather_ctx=weather_ctx,
                emotion_ctx=emotion_ctx,
            )
        if not str(content or "").strip():
            content = _build_derivative_text_fallback(
                dtype="novel",
                diary_excerpt=diary_excerpt,
                weather_ctx=weather_ctx,
                emotion_ctx=emotion_ctx,
            )
    elif dtype == "share_card":
        system_prompt = (
            "你是社交平台分享文案编辑。"
            "请稳定输出温暖、克制、可发布的朋友圈风格文案。"
            "输出要求：\n"
            "1. 30-80 字；\n"
            "2. 1 段正文，不换行，不加标题；\n"
            "3. 可以使用 0-2 个 emoji；\n"
            "4. 不用 hashtag，不用营销口吻；\n"
            "5. 内容必须基于日记事实并体现当天情绪。"
        )
        user_prompt = (
            f"请根据以下日记生成分享卡文案。天气：{weather_ctx}；主要情绪：{emotion_ctx}。\n\n"
            f"日记内容：\n{diary_excerpt}"
        )
        messages = [{"role": "user", "content": user_prompt}]
        try:
            content = await asyncio.wait_for(
                client.chat_completion(messages, system_prompt=system_prompt, temperature=0.55),
                timeout=DERIVATIVE_AI_TIMEOUT_SEC,
            )
        except Exception:
            content = _build_derivative_text_fallback(
                dtype="share_card",
                diary_excerpt=diary_excerpt,
                weather_ctx=weather_ctx,
                emotion_ctx=emotion_ctx,
            )
        if not str(content or "").strip():
            content = _build_derivative_text_fallback(
                dtype="share_card",
                diary_excerpt=diary_excerpt,
                weather_ctx=weather_ctx,
                emotion_ctx=emotion_ctx,
            )

    from app.models.derivative import DiaryDerivative
    deriv = DiaryDerivative(
        id=_uuid(),
        diary_id=target_diary_id,
        type=dtype,
        content=content,
        media_url=media_url,
        share_scope="private",
        created_at=now,
    )
    db.add(deriv)
    db.commit()
    db.refresh(deriv)

    from app.diary.schemas import DerivativeOut
    return DerivativeOut(
        id=deriv.id,
        diary_id=target_diary_id,
        type=dtype,
        content=content,
        media_url=media_url,
        share_scope="private",
        created_at=now,
    ).model_dump(by_alias=True)


def start_derivative_task(db: Session, user_id: str, diary_id: str, dtype: str) -> dict:
    """创建异步衍生内容任务，当前用于漫画生成。"""
    allowed_types = {"comic"}
    if dtype not in allowed_types:
        raise ApiException(
            code=PARAM_ERROR,
            message=f"异步衍生任务暂仅支持 comic，当前为: {dtype}",
            status_code=400,
        )

    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d and str(diary_id).strip() == "1":
        d = (
            db.query(Diary)
            .filter(Diary.user_id == user_id)
            .order_by(Diary.created_at.desc())
            .first()
        )
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    _prune_derivative_tasks()
    for task in _DERIVATIVE_TASKS.values():
        if (
            task.get("user_id") == user_id
            and task.get("diary_id") == d.id
            and task.get("type") == dtype
            and task.get("status") == "running"
        ):
            return _derivative_task_to_dict(task)

    now = _now_ms()
    task = {
        "task_id": _uuid(),
        "user_id": user_id,
        "diary_id": d.id,
        "type": dtype,
        "status": "running",
        "derivative_id": None,
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    _DERIVATIVE_TASKS[task["task_id"]] = task
    return _derivative_task_to_dict(task)


def get_derivative_task(user_id: str, task_id: str) -> dict:
    _prune_derivative_tasks()
    task = _DERIVATIVE_TASKS.get(task_id)
    if not task or task.get("user_id") != user_id:
        raise ApiException(code=NOT_FOUND, message="衍生任务不存在", status_code=404)
    return _derivative_task_to_dict(task)


async def run_derivative_task(task_id: str) -> None:
    """后台执行衍生内容生成任务。"""
    from app.database import SessionLocal

    task = _DERIVATIVE_TASKS.get(task_id)
    if not task:
        return

    db = SessionLocal()
    try:
        result = await generate_derivative(
            db,
            str(task.get("user_id") or ""),
            str(task.get("diary_id") or ""),
            str(task.get("type") or ""),
        )
        task["status"] = "done"
        task["derivative_id"] = result.get("id")
        task["error"] = ""
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)[:200] or "生成失败"
    finally:
        task["updated_at"] = _now_ms()
        db.close()


# ==================== 补写日记（历史日记） ====================

BACKFILL_TASK_TTL_MS = 60 * 60 * 1000
_BACKFILL_TASKS: dict[str, dict] = {}
BACKFILL_MAX_PHOTOS = 9
BACKFILL_VISION_PROMPT = (
    "请客观描述这张照片的画面内容：场景、人物、动作、物品、氛围与可见的时间或天气线索，"
    "用一两句中文概括，不要臆造照片以外的信息。"
)


def _prune_backfill_tasks(now: Optional[int] = None) -> None:
    current = now or _now_ms()
    expired = [
        task_id
        for task_id, task in _BACKFILL_TASKS.items()
        if current - int(task.get("updated_at") or task.get("created_at") or 0) > BACKFILL_TASK_TTL_MS
    ]
    for task_id in expired:
        _BACKFILL_TASKS.pop(task_id, None)


def _backfill_task_to_dict(task: dict) -> dict:
    results = task.get("results") or []
    primary = results[0]["diary_id"] if results else task.get("diary_id")
    return {
        "task_id": task.get("task_id"),
        "date": task.get("date"),
        "status": task.get("status"),
        "diary_id": primary,
        "results": results,
        "error": task.get("error") or "",
        "created_at": int(task.get("created_at") or 0),
        "updated_at": int(task.get("updated_at") or task.get("created_at") or 0),
    }


def _backfill_period_label(ts: int) -> str:
    """根据毫秒时间戳推断时间段标签。"""
    try:
        hour = datetime.fromtimestamp(ts / 1000).hour
    except Exception:
        return "某个时刻"
    if 5 <= hour < 9:
        return "清晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 20:
        return "傍晚"
    if 20 <= hour < 24:
        return "夜晚"
    return "深夜"


def _normalize_backfill_payload(payload) -> dict:
    """统一补写请求结构为内部 dict，兼容 pydantic 模型与 dict。"""
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {}

    date = str(data.get("date") or "").strip()
    raw_photos = data.get("photos") or []
    photos = []
    for item in raw_photos:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        try:
            taken_at = int(item.get("taken_at") or item.get("takenAt") or 0)
        except Exception:
            taken_at = 0
        photos.append({
            "url": url,
            "taken_at": taken_at,
            "user_note": str(item.get("user_note") or item.get("userNote") or "").strip(),
            "location": str(item.get("location") or "").strip(),
        })

    return {
        "date": date,
        "photos": photos[:BACKFILL_MAX_PHOTOS],
        "interview_transcript": str(data.get("interview_transcript") or data.get("interviewTranscript") or "").strip(),
        "weather": str(data.get("weather") or "").strip(),
    }


def _build_backfill_materials_text(date: str, photos: List[dict], vision_hints: List[str], interview: str) -> str:
    """把照片视觉理解、用户回忆与分身访谈拼装成 generate_diary 可用的素材文本。"""
    lines: List[str] = [f"这是一篇{date}的补写日记，请基于以下回忆素材还原当天的真实经历。"]
    for idx, photo in enumerate(photos):
        ts = photo.get("taken_at") or 0
        try:
            time_label = datetime.fromtimestamp(ts / 1000).strftime("%H:%M") if ts else "时间未知"
        except Exception:
            time_label = "时间未知"
        period = _backfill_period_label(ts) if ts else ""
        vision = (vision_hints[idx] if idx < len(vision_hints) else "") or ""
        note = photo.get("user_note") or ""
        location = photo.get("location") or ""
        parts = [f"{time_label}（{period}）照片{idx + 1}"]
        if vision.strip():
            parts.append(f"画面：{vision.strip()}")
        if note.strip():
            parts.append(f"我的回忆：{note.strip()}")
        if location.strip():
            parts.append(f"地点：{location.strip()}")
        lines.append("- " + "；".join(parts))

    if interview.strip():
        lines.append("")
        lines.append("【与 AI 分身回忆这一天的补充对话】")
        lines.append(interview.strip())

    return "\n".join(lines)


def _date_from_ts(ts: int) -> str:
    """毫秒时间戳 → YYYY-MM-DD。"""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _group_photos_by_date(photos: List[dict], fallback_date: str) -> dict:
    """按拍摄日期分组照片；缺失拍摄时间的归入 fallback_date。"""
    groups: dict = {}
    for photo in photos:
        ts = photo.get("taken_at") or 0
        date = _date_from_ts(ts) if ts > 0 else (fallback_date or "")
        if not date:
            continue
        groups.setdefault(date, []).append(photo)
    return groups


def validate_backfill_request(db: Session, user_id: str, payload) -> dict:
    """校验补写请求并返回归一化数据。已有日记的日期将走合并逻辑，不再拒绝。"""
    data = _normalize_backfill_payload(payload)
    if not data["photos"]:
        raise ApiException(code=PARAM_ERROR, message="请至少上传一张照片", status_code=400)
    # date 缺省时由照片拍摄时间推导，最终在任务里按天分组。
    if not data["date"]:
        first_ts = next((p.get("taken_at") for p in data["photos"] if p.get("taken_at")), 0)
        data["date"] = _date_from_ts(first_ts) if first_ts else datetime.now().strftime("%Y-%m-%d")
    return data


def start_backfill_task(db: Session, user_id: str, payload) -> dict:
    """创建异步补写日记任务。"""
    data = validate_backfill_request(db, user_id, payload)

    _prune_backfill_tasks()
    now = _now_ms()
    task = {
        "task_id": _uuid(),
        "user_id": user_id,
        "date": data["date"],
        "payload": data,
        "status": "running",
        "diary_id": None,
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    _BACKFILL_TASKS[task["task_id"]] = task
    return _backfill_task_to_dict(task)


def get_backfill_task(user_id: str, task_id: str) -> dict:
    _prune_backfill_tasks()
    task = _BACKFILL_TASKS.get(task_id)
    if not task or task.get("user_id") != user_id:
        raise ApiException(code=NOT_FOUND, message="补写任务不存在", status_code=404)
    return _backfill_task_to_dict(task)


async def _create_backfill_diary(
    db: Session,
    user_id: str,
    date: str,
    photos: List[dict],
    interview_transcript: str = "",
    weather: str = "",
) -> dict:
    """为指定日期执行补写：vision 批量理解 → 文本生成 → 写库/合并。

    返回 {"date", "diary_id", "merged"}。
    若该日期已存在日记，则把新内容追加到原日记（合并），并补充图片。
    """
    photos = sorted(photos, key=lambda p: p.get("taken_at") or 0)
    image_urls = [p["url"] for p in photos]

    from app.ai import service as ai_service

    vision_hints: List[str] = []
    try:
        vision_hints = await ai_service.understand_images_batch(image_urls, prompt=BACKFILL_VISION_PROMPT)
    except Exception:
        vision_hints = []

    materials_text = _build_backfill_materials_text(
        date, photos, vision_hints, interview_transcript
    )

    user = db.query(User).filter(User.id == user_id).first()
    user_style = ""
    if user and user.style_tags:
        try:
            tags = json.loads(user.style_tags)
            user_style = "、".join(tags) if tags else ""
        except Exception:
            pass

    image_understandings = [str(h or "").strip() for h in vision_hints][: len(image_urls)]

    # 历史时间：取当天最后一张照片的拍摄时间；若缺失则落到当天 23:59。
    last_taken = max((p.get("taken_at") or 0) for p in photos) if photos else 0
    if last_taken <= 0:
        try:
            day_dt = datetime.strptime(date, "%Y-%m-%d").replace(hour=23, minute=59)
            last_taken = int(day_dt.timestamp() * 1000)
        except Exception:
            last_taken = _now_ms()

    locations = [p.get("location") for p in photos if p.get("location")]
    diary_location = locations[0] if locations else ""

    # ── 合并分支：该日期已有日记，追加内容与图片 ──
    existing = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .first()
    )
    if existing:
        from app.ai.minimax_client import get_minimax_client
        client = get_minimax_client()
        merge_materials = (
            f"以下是这一天已有的日记正文：\n{existing.content or '（无）'}\n\n"
            f"现在补充了这一天的更多照片与回忆，请把它们自然地融合进原日记，"
            f"保持时间顺序与真实事实，输出整合后的完整日记：\n{materials_text}"
        )
        result = await client.generate_diary(
            merge_materials,
            weather=weather or existing.weather or "",
            user_style=user_style,
            diary_date=date,
        )
        merged_images = _decode(existing.images, []) + [u for u in image_urls if u not in _decode(existing.images, [])]
        merged_understandings = _decode(existing.image_understandings, []) + image_understandings
        existing.content = result.get("content", existing.content) or existing.content
        existing.images = _encode(merged_images)
        existing.image_understandings = _encode(merged_understandings)
        if not existing.location and diary_location:
            existing.location = diary_location
        new_tags = result.get("ai_tags") or []
        if isinstance(new_tags, list) and new_tags:
            merged_tags = _decode(existing.tags, []) + [t for t in new_tags if t not in _decode(existing.tags, [])]
            existing.tags = _encode(merged_tags)
        existing.updated_at = _now_ms()
        db.commit()
        db.refresh(existing)
        try:
            from app.memory.ingestion import ingest_diary
            ingest_diary(db, existing)
        except Exception:
            pass
        return {"date": date, "diary_id": existing.id, "merged": True}

    # ── 新建分支 ──
    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.generate_diary(
        materials_text,
        weather=weather or "",
        user_style=user_style,
        diary_date=date,
    )

    emotion_summary = result.get("emotion_summary") or {}
    if not isinstance(emotion_summary, dict):
        emotion_summary = {}
    dominant = str(emotion_summary.get("dominant") or "平静").strip() or "平静"
    emotion_payload = {
        "emoji": DEFAULT_EMOTION_EMOJI.get(dominant, "😐"),
        "label": dominant,
        "score": 0,
    }
    ai_tags = result.get("ai_tags") or []
    if not isinstance(ai_tags, list):
        ai_tags = []

    d = Diary(
        id=_uuid(),
        user_id=user_id,
        content=result.get("content", ""),
        title=result.get("title", "补写日记"),
        images=_encode(image_urls),
        image_understandings=_encode(image_understandings),
        emotion=_encode(emotion_payload),
        tags=_encode(ai_tags),
        weather=weather or "",
        location=diary_location,
        date=date,
        material_ids=_encode([]),
        emotion_summary=_encode(emotion_summary),
        status="draft",
        edit_count=0,
        max_edits=DIARY_MAX_EDITS,
        created_at=last_taken,
        updated_at=_now_ms(),
    )
    db.add(d)
    if user:
        user.diary_count = (user.diary_count or 0) + 1
    try:
        db.commit()
    except IntegrityError:
        # 并发兜底：写库前被其它请求抢先创建，退回合并。
        db.rollback()
        existing = (
            db.query(Diary)
            .filter(Diary.user_id == user_id, Diary.date == date)
            .first()
        )
        if existing:
            return {"date": date, "diary_id": existing.id, "merged": True}
        raise

    db.refresh(d)

    # AI 分身点评（与正常日记一致），失败不阻断。
    try:
        ai_comment = await _generate_ai_comment_for_diary(
            db, user_id, d, [], materials_text=materials_text
        )
        if ai_comment:
            d.ai_comment = ai_comment
            d.updated_at = _now_ms()
            db.commit()
            db.refresh(d)
    except Exception:
        pass

    try:
        from app.memory.ingestion import ingest_diary
        ingest_diary(db, d)
    except Exception:
        pass

    return {"date": date, "diary_id": d.id, "merged": False}


async def run_backfill_task(task_id: str) -> None:
    """后台执行补写日记任务：按拍摄日期分组，逐日创建或合并。"""
    from app.database import SessionLocal

    task = _BACKFILL_TASKS.get(task_id)
    if not task:
        return

    db = SessionLocal()
    try:
        data = task.get("payload") or {}
        user_id = str(task.get("user_id") or "")
        groups = _group_photos_by_date(data.get("photos") or [], data.get("date") or "")
        if not groups:
            raise ApiException(code=PARAM_ERROR, message="无有效照片", status_code=400)

        results: List[dict] = []
        # 访谈素材整体附加到第一天（按日期升序）。
        interview = data.get("interview_transcript") or ""
        for idx, date in enumerate(sorted(groups.keys())):
            res = await _create_backfill_diary(
                db,
                user_id,
                date,
                groups[date],
                interview_transcript=interview if idx == 0 else "",
                weather=data.get("weather") or "",
            )
            results.append(res)

        task["results"] = results
        task["status"] = "done"
        task["error"] = ""
    except ApiException as exc:
        task["status"] = "failed"
        task["error"] = (exc.message or "补写失败")[:200]
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)[:200] or "补写失败"
    finally:
        task["updated_at"] = _now_ms()
        db.close()


def _build_backfill_interview_prompt(data: dict) -> str:
    """把照片素材整理成给分身访谈用的上下文。"""
    photos = sorted(data["photos"], key=lambda p: p.get("taken_at") or 0)
    lines = [f"用户正在补写 {data['date']} 的日记，已上传以下照片与回忆："]
    for idx, photo in enumerate(photos):
        note = photo.get("user_note") or "（暂无描述）"
        lines.append(f"{idx + 1}. {note}")
    return "\n".join(lines)


BACKFILL_INTERVIEW_SYSTEM = (
    "你是用户的 AI 分身，正在像老朋友一样帮 TA 回忆过去某一天的细节，以便补写日记。\n"
    "你会看到：用户上传的照片对应的简单回忆。\n"
    "你的任务：\n"
    "1. 用温和、好奇、亲切的语气，针对模糊或缺失的细节追问，一次只问一个问题；\n"
    "2. 优先问：在场的人、心情变化、关键对话、印象最深的瞬间、感官细节（声音/味道/天气）；\n"
    "3. 收到回答后，先用一句话简短回应，再自然地问下一个问题，不要说教；\n"
    "4. 当已经问满 5 个问题，或用户表示“够了/可以了/没有了”，输出一句温暖的收束语，并在末尾追加标记 [INTERVIEW_DONE]。"
)


async def stream_backfill_interview(user_id: str, payload):
    """AI 分身追问素材扩展，SSE 流式返回分身的下一句话。"""
    from app.ai.minimax_client import get_minimax_client

    yield _sse_event({"type": "start"})

    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    else:
        data = dict(payload or {})

    norm = _normalize_backfill_payload({
        "date": data.get("date"),
        "photos": data.get("photos") or [],
    })
    raw_messages = data.get("messages") or []
    history = []
    for msg in raw_messages:
        if hasattr(msg, "model_dump"):
            msg = msg.model_dump()
        role = str((msg or {}).get("role") or "").strip()
        content = str((msg or {}).get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content})

    context = _build_backfill_interview_prompt(norm)
    messages = [{"role": "user", "content": context}]
    messages.extend(history)
    if not history or history[-1]["role"] == "assistant":
        # 首轮或需要分身继续提问时，补一句引导。
        messages.append({"role": "user", "content": "请基于以上信息，向我提出下一个帮助回忆的问题。"})

    client = get_minimax_client()
    full_reply = ""
    try:
        try:
            async for chunk in client.stream_chat(messages, system_prompt=BACKFILL_INTERVIEW_SYSTEM):
                if not chunk:
                    continue
                full_reply += chunk
                yield _sse_event({"type": "chunk", "text": chunk})
        except Exception:
            fallback = await client.chat_completion(messages, system_prompt=BACKFILL_INTERVIEW_SYSTEM)
            full_reply = fallback or ""
            if full_reply:
                yield _sse_event({"type": "chunk", "text": full_reply})

        done = "[INTERVIEW_DONE]" in full_reply
        clean_reply = full_reply.replace("[INTERVIEW_DONE]", "").strip()
        yield _sse_event({"type": "done", "text": clean_reply, "finished": done})
    except Exception as exc:
        yield _sse_event({"type": "error", "message": str(exc)})


BACKFILL_QUESTIONS_SYSTEM = (
    "你是用户的 AI 分身，正在帮 TA 回忆过去某一天的细节，以便补写日记。\n"
    "请根据用户上传的照片与简单回忆，一次性设计 3~5 个温和、具体、便于回答的问题，"
    "帮助 TA 把这一天回忆得更完整。\n"
    "要求：\n"
    "1. 问题要具体、贴合照片内容，避免空泛（如不要只问“当时心情如何”）；\n"
    "2. 覆盖：在场的人、关键事件、心情变化、印象最深的瞬间、感官细节（声音/味道/天气）；\n"
    "3. 每个问题一句话，口语化、亲切；\n"
    "4. 严格只输出 JSON 数组，形如 [\"问题1\",\"问题2\",\"问题3\"]，不要输出任何解释或 markdown。"
)

BACKFILL_DEFAULT_QUESTIONS = [
    "这一天你主要和谁在一起？当时的氛围是怎样的？",
    "照片里发生的事，让你印象最深的瞬间是什么？",
    "那天你的心情有什么变化吗？是什么让你有这种感觉？",
    "有没有什么细节（一句话、一种味道、一段声音）现在还记得？",
]


async def generate_backfill_questions(user_id: str, payload) -> dict:
    """根据照片与回忆，一次性预生成 3~5 个访谈问题，供前端问卷式收集。"""
    from app.ai.minimax_client import get_minimax_client

    norm = _normalize_backfill_payload(payload)
    if not norm["photos"]:
        return {"questions": BACKFILL_DEFAULT_QUESTIONS[:3]}

    context = _build_backfill_interview_prompt(norm)
    messages = [{"role": "user", "content": context + "\n\n请为我设计帮助回忆这一天的问题。"}]
    client = get_minimax_client()
    try:
        resp = await client.chat_completion(
            messages, system_prompt=BACKFILL_QUESTIONS_SYSTEM, temperature=0.7
        )
        raw = (resp or "").strip()
        questions: List[str] = []
        try:
            parsed = json.loads(raw)
        except Exception:
            match = re.search(r"\[[\s\S]*\]", raw)
            parsed = json.loads(match.group(0)) if match else []
        if isinstance(parsed, list):
            questions = [str(q).strip() for q in parsed if str(q).strip()]
        questions = questions[:5]
        if not questions:
            questions = BACKFILL_DEFAULT_QUESTIONS[:4]
        return {"questions": questions}
    except Exception:
        return {"questions": BACKFILL_DEFAULT_QUESTIONS[:4]}



def get_today_summary(db: Session, user_id: str, date: str) -> dict:
    """今日概要：素材数 + 素材列表 + 是否已生成日记"""
    materials_query = db.query(RawMaterial).filter(RawMaterial.user_id == user_id)
    materials = (
        _apply_material_date_filter(materials_query, date)
        .order_by(RawMaterial.created_at)
        .all()
    )

    from app.material.service import _decode as mat_decode
    mat_list = []
    for m in materials:
        em = mat_decode(m.emotion, {})
        mat_list.append({
            "id": m.id,
            "type": m.type,
            "content": m.content or "",
            "createdAt": m.created_at,
            "emotion": em if em else None,
        })

    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .order_by(Diary.created_at.desc())
        .all()
    )
    diary = diaries[0] if diaries else None

    emotion_counter: Counter[str] = Counter()
    for diary_item in diaries:
        summary = _decode(diary_item.emotion_summary, {})
        dominant = str(summary.get("dominant") or "").strip() if isinstance(summary, dict) else ""
        if not dominant:
            legacy_emotion = _decode(diary_item.emotion, {})
            dominant = str(legacy_emotion.get("label") or "").strip() if isinstance(legacy_emotion, dict) else ""
        if dominant:
            emotion_counter[dominant] += 1

    if not emotion_counter:
        for material in materials:
            material_emotion = mat_decode(material.emotion, {})
            label = str(material_emotion.get("label") or "").strip() if isinstance(material_emotion, dict) else ""
            if label:
                emotion_counter[label] += 1

    dominant_emotion = emotion_counter.most_common(1)[0][0] if emotion_counter else ""

    user = db.query(User).filter(User.id == user_id).first()
    greeting_user_name = "同学"
    if user:
        greeting_user_name = (user.name or "").strip() or (user.username or "").strip() or "同学"

    diary_count = len(diaries)

    return {
        "date": date,
        "material_count": len(materials),
        "materials": mat_list,
        "has_diary": diary is not None,
        "diary_id": diary.id if diary else None,
        "diary_status": diary.status if diary else None,
        "greeting_user_name": greeting_user_name,
        "diary_count": diary_count,
        "dominant_emotion": dominant_emotion,
    }


def delete_diary(db: Session, user_id: str, diary_id: str) -> None:
    """删除日记"""
    d = db.query(Diary).filter(
        Diary.id == diary_id,
        Diary.user_id == user_id,
    ).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)
    db.delete(d)
    db.commit()
