"""
日记模块服务层 v2
实现日记 CRUD + AI 生成 + 衍生内容逻辑
"""
import json
import time
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.diary import Diary
from app.models.material import RawMaterial
from app.response import ApiException, NOT_FOUND, PARAM_ERROR


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
        "max_edits": d.max_edits or 3,
        "status": d.status or "draft",
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        # legacy 兼容
        "emotion": emotion,
        "images": _decode(d.images, []),
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

    if (d.edit_count or 0) >= (d.max_edits or 3):
        raise ApiException(
            code=PARAM_ERROR,
            message=f"日记最多只能修改 {d.max_edits} 次，已达上限",
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


async def generate_diary(db: Session, user_id: str, date: str, weather: str = "") -> dict:
    """AI 生成当日日记"""
    materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id, RawMaterial.date == date)
        .order_by(RawMaterial.created_at)
        .all()
    )

    parts = []
    for m in materials:
        if m.type == "text" and m.content:
            parts.append(f"[文字] {m.content}")
        elif m.type == "image" and m.content:
            parts.append(f"[图片描述] {m.content}")
        elif m.type == "voice" and m.content:
            parts.append(f"[语音转文字] {m.content}")
    materials_text = "\n".join(parts) if parts else f"今天是 {date}，无具体素材记录。"

    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    user_style = ""
    if user and user.style_tags:
        try:
            tags = json.loads(user.style_tags)
            user_style = "、".join(tags) if tags else ""
        except Exception:
            pass

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.generate_diary(materials_text, weather=weather, user_style=user_style)

    now = _now_ms()
    material_ids = [m.id for m in materials]
    emotion_summary = result.get("emotion_summary", {"dominant": "平静", "trend": []})

    d = Diary(
        id=_uuid(),
        user_id=user_id,
        content=result.get("content", ""),
        title=result.get("title", "今日日记"),
        images=_encode([]),
        emotion=_encode({"emoji": "😊", "label": emotion_summary.get("dominant", "平静"), "score": 70}),
        tags=_encode([]),
        weather=weather,
        date=date,
        material_ids=_encode(material_ids),
        emotion_summary=_encode(emotion_summary),
        status="draft",
        edit_count=0,
        max_edits=3,
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    if user:
        user.diary_count = (user.diary_count or 0) + 1
    db.commit()
    db.refresh(d)
    from app.diary.schemas import DiaryOut
    return DiaryOut(**diary_to_dict(d)).model_dump(by_alias=True)


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

    trend = []
    emotion_counts = {}
    for m in materials:
        em = _decode(m.emotion, {})
        if em.get("label"):
            import datetime
            # Use created_at hour
            hour = datetime.datetime.fromtimestamp(m.created_at / 1000).hour
            score_raw = em.get("score", 0.5)
            # Convert 0-1 score to 0-100
            score_int = int(score_raw * 100) if score_raw <= 1 else int(score_raw)
            trend.append({
                "hour": hour,
                "label": em["label"],
                "score": score_int,
            })
            emotion_counts[em["label"]] = emotion_counts.get(em["label"], 0) + 1

    dominant = max(emotion_counts, key=emotion_counts.get) if emotion_counts else ""
    return {"dominant": dominant, "trend": trend}


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
    for item in result.get("anniversaries", []):
        if item.get("title") and item.get("date"):
            ann = Anniversary(
                id=_uuid(),
                user_id=user_id,
                title=item["title"],
                date=item["date"],
                source="ai_extracted",
                related_person=item.get("relatedPerson", item.get("related_person", "")),
                diary_id=diary_id,
                created_at=now,
            )
            db.add(ann)
            anniversaries_out.append({
                "title": item["title"],
                "date": item["date"],
                "relatedPerson": item.get("relatedPerson", item.get("related_person", "")),
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

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()

    content = ""
    media_url = ""
    now = _now_ms()

    if dtype == "comic":
        prompt = f"将以下日记内容绘制成温暖可爱的漫画风格插图：{(d.content or '')[:200]}"
        media_url = await client.generate_image(prompt, aspect_ratio="1:1")
    elif dtype == "novel":
        messages = [{"role": "user", "content": f"将以下日记改写成有趣的短篇小说（300字）：\n\n{d.content}"}]
        content = await client.chat_completion(messages, temperature=0.9)
    elif dtype == "share_card":
        messages = [{"role": "user", "content": f"为以下日记生成一段适合朋友圈分享的文案（80字以内）：\n\n{d.content}"}]
        content = await client.chat_completion(messages, temperature=0.8)

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
    materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id, RawMaterial.date == date)
        .order_by(RawMaterial.created_at)
        .all()
    )

    from app.material.service import _decode as mat_decode, _encode as mat_encode
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
