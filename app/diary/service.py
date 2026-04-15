"""
日记模块服务层 v2
实现日记 CRUD + AI 生成 + 衍生内容逻辑
"""
import json
import os
import re
import time
from datetime import datetime
from typing import List
from uuid import uuid4

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.diary import Diary
from app.models.material import RawMaterial
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


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def _apply_material_date_filter(query, date: str):
    """兼容 RawMaterial.date 的按天筛选（YYYY-MM-DD）与精确到秒筛选。"""
    date_value = (date or "").strip()
    if len(date_value) == 10:
        return query.filter(RawMaterial.date.like(f"{date_value}%"))
    return query.filter(RawMaterial.date == date_value)


def _score_to_int(score_raw) -> int:
    """将 0-1 或 0-100 的情绪分统一为 0-100 整数。"""
    try:
        score = float(score_raw)
    except Exception:
        score = 50.0

    if score <= 1:
        score *= 100

    score_int = int(score)
    return max(0, min(100, score_int))


def _build_emotion_trend_from_materials(materials: List[RawMaterial]) -> dict:
    """基于素材列表聚合当日情绪趋势。"""
    trend = []
    emotion_counts = {}

    for m in materials:
        em = _decode(m.emotion, {})
        label = (em.get("label") or "").strip()
        if not label:
            continue

        hour = datetime.fromtimestamp(m.created_at / 1000).hour if m.created_at else 0
        score_int = _score_to_int(em.get("score", 0.5))

        trend.append({
            "hour": hour,
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
        item.get("score", 50)
        for item in trend
        if item.get("label") == dominant
    ]
    if not scores:
        scores = [item.get("score", 50) for item in trend]
    score = int(sum(scores) / len(scores)) if scores else 50

    emoji = ""
    for m in materials:
        em = _decode(m.emotion, {})
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
            time_range = ""
            if m.start_time and m.end_time:
                s = datetime.fromtimestamp(m.start_time / 1000).strftime("%H:%M")
                e = datetime.fromtimestamp(m.end_time / 1000).strftime("%H:%M")
                time_range = f"({s}~{e}) "
            parts.append(f"[对话记录] {time_range}{m.content}")

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
        prompt=settings.ARK_VISION_PROMPT,
        timeout_sec=int(settings.ARK_VISION_TIMEOUT_SEC),
        max_images=len(image_entries),
    )

    hints: dict = {}
    for idx, (material_id, _image_url) in enumerate(image_entries):
        description = ""
        if idx < len(results):
            description = str(results[idx].get("description") or "").strip()
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
    emotion_summary = _decode(d.emotion_summary, {})
    # 从 emotion_summary 提取 legacy emotion 字段
    dominant = emotion_summary.get("dominant", "")
    trend = emotion_summary.get("trend", [])
    legacy_score = trend[0]["score"] if trend else 50
    emotion = _decode(d.emotion, {
        "emoji": "😐",
        "label": dominant or "平静",
        "score": legacy_score,
    })
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
    from app.diary.schemas import DiaryOut
    return DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True)


async def generate_diary(
    db: Session,
    user_id: str,
    date: str,
    weather: str = "",
    allow_fallback: bool = False,
) -> dict:
    """AI 生成当日日记"""
    normalized_weather = _normalize_weather_text(weather)

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

    from app.models.user import User
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
    )

    now = _now_ms()
    material_ids = [m.id for m in materials]
    emotion_summary = emotion_summary_for_prompt
    emotion_payload = _build_legacy_emotion_payload(emotion_summary, materials)
    diary_images = _collect_today_image_urls(materials)
    material_tags = _collect_today_material_tags(materials)
    ai_tags = _extract_ai_tags(result, normalized_weather, emotion_summary)
    diary_tags = _merge_diary_tags(material_tags, ai_tags)

    # 同一天已有日记时，更新而不是新建
    existing = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .first()
    )

    if existing:
        existing.content = result.get("content", "")
        existing.title = result.get("title", "今日日记")
        existing.weather = normalized_weather
        existing.material_ids = _encode(material_ids)
        existing.emotion_summary = _encode(emotion_summary)
        existing.emotion = _encode(emotion_payload)
        existing.images = _encode(diary_images)
        existing.image_understandings = _encode(image_understandings)
        existing.tags = _encode(diary_tags)
        existing.status = "draft"
        existing.updated_at = now

        db.commit()

        # 通过“当日情绪趋势”逻辑再次聚合，作为最终 emotion/emotion_summary。
        trend_summary = get_emotion_trend(db, user_id, existing.id)
        existing.emotion_summary = _encode(trend_summary)
        existing.emotion = _encode(_build_legacy_emotion_payload(trend_summary, materials))
        existing.updated_at = _now_ms()
        db.commit()

        db.refresh(existing)
        from app.diary.schemas import DiaryOut

        payload = DiaryOut(**diary_to_dict(existing)).model_dump(by_alias=True)
        payload["imageUnderstandings"] = image_understandings
        return payload

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
    db.commit()

    # 通过“当日情绪趋势”逻辑再次聚合，作为最终 emotion/emotion_summary。
    trend_summary = get_emotion_trend(db, user_id, d.id)
    d.emotion_summary = _encode(trend_summary)
    d.emotion = _encode(_build_legacy_emotion_payload(trend_summary, materials))
    d.updated_at = _now_ms()
    db.commit()

    db.refresh(d)
    from app.diary.schemas import DiaryOut

    payload = DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True)
    payload["imageUnderstandings"] = image_understandings
    return payload


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

    material_ids = _decode(d.material_ids, [])
    if not material_ids:
        return {"dominant": "", "trend": []}

    materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.id.in_(material_ids))
        .order_by(RawMaterial.created_at)
        .all()
    )
    return _build_emotion_trend_from_materials(materials)


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
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

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

    emotion_ctx = _decode(d.emotion_summary, {}).get("dominant", "") or "平静"
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
        media_url = await client.generate_image(prompt, aspect_ratio="1:1")
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
        content = await client.chat_completion(messages, system_prompt=system_prompt, temperature=0.65)
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
        content = await client.chat_completion(messages, system_prompt=system_prompt, temperature=0.55)

    from app.models.derivative import DiaryDerivative
    deriv = DiaryDerivative(
        id=_uuid(),
        diary_id=diary_id,
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
        diary_id=diary_id,
        type=dtype,
        content=content,
        media_url=media_url,
        share_scope="private",
        created_at=now,
    ).model_dump(by_alias=True)


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

    diary = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .first()
    )

    return {
        "date": date,
        "material_count": len(materials),
        "materials": mat_list,
        "has_diary": diary is not None,
        "diary_id": diary.id if diary else None,
        "diary_status": diary.status if diary else None,
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
