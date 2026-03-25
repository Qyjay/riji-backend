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
    """日记模型转响应字典"""
    return {
        "id": d.id,
        "user_id": d.user_id,
        "content": d.content or "",
        "title": d.title or "",
        "images": _decode(d.images, []),
        "emotion": _decode(d.emotion, {}),
        "tags": _decode(d.tags, []),
        "location": d.location or "",
        "weather": d.weather or "",
        "style": d.style or "日记式",
        "has_comic": d.has_comic or False,
        "has_bgm": d.has_bgm or False,
        "comic_url": d.comic_url or "",
        "bgm_url": d.bgm_url or "",
        "created_at": d.created_at,
        "updated_at": d.updated_at,
        "special_date": d.special_date or "",
        "emotion_summary": _decode(d.emotion_summary, {}),
        "material_ids": _decode(d.material_ids, []),
        "edit_count": d.edit_count or 0,
        "max_edits": d.max_edits or 3,
        "status": d.status or "draft",
        "date": d.date or "",
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
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [diary_to_dict(d) for d in diaries],
    }


def get_diary(db: Session, user_id: str, diary_id: str) -> dict:
    """获取单篇日记"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)
    return diary_to_dict(d)


def create_diary(db: Session, user_id: str, data: dict) -> dict:
    """手动创建日记"""
    now = _now_ms()
    d = Diary(
        id=_uuid(),
        user_id=user_id,
        content=data["content"],
        images=_encode(data.get("images", [])),
        emotion=_encode(data.get("emotion", {})),
        tags=_encode(data.get("tags", [])),
        location=data.get("location", ""),
        weather=data.get("weather", ""),
        style=data.get("style", "日记式"),
        created_at=now,
        updated_at=now,
        title="",
        date=data.get("date", ""),
        status="draft",
    )
    db.add(d)
    # 更新用户日记数量
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.diary_count = (user.diary_count or 0) + 1
    db.commit()
    db.refresh(d)
    return diary_to_dict(d)


def update_diary(db: Session, user_id: str, diary_id: str, data: dict) -> dict:
    """更新日记（检查修改次数限制）"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    # 检查修改次数
    if (d.edit_count or 0) >= (d.max_edits or 3):
        raise ApiException(
            code=PARAM_ERROR,
            message=f"日记最多只能修改 {d.max_edits} 次，已达上限",
            status_code=400,
        )

    if "content" in data and data["content"] is not None:
        d.content = data["content"]
    if "images" in data and data["images"] is not None:
        d.images = _encode(data["images"])
    if "emotion" in data and data["emotion"] is not None:
        d.emotion = _encode(data["emotion"])
    if "tags" in data and data["tags"] is not None:
        d.tags = _encode(data["tags"])
    if "location" in data and data["location"] is not None:
        d.location = data["location"]
    if "weather" in data and data["weather"] is not None:
        d.weather = data["weather"]
    if "title" in data and data["title"] is not None:
        d.title = data["title"]

    d.edit_count = (d.edit_count or 0) + 1
    d.updated_at = _now_ms()
    db.commit()
    db.refresh(d)
    return diary_to_dict(d)


def delete_diary(db: Session, user_id: str, diary_id: str) -> None:
    """删除日记"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)
    db.delete(d)
    # 更新用户日记数量
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.diary_count = max(0, (user.diary_count or 0) - 1)
    db.commit()


async def generate_diary(db: Session, user_id: str, date: str, weather: str = "") -> dict:
    """AI 生成当日日记"""
    # 获取当天素材
    materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id, RawMaterial.date == date)
        .order_by(RawMaterial.created_at)
        .all()
    )

    # 组装素材文本
    parts = []
    for m in materials:
        if m.type == "text" and m.content:
            parts.append(f"[文字] {m.content}")
        elif m.type == "image" and m.content:
            parts.append(f"[图片描述] {m.content}")
        elif m.type == "voice" and m.content:
            parts.append(f"[语音转文字] {m.content}")
    materials_text = "\n".join(parts) if parts else f"今天是 {date}，无具体素材记录。"

    # 获取用户写作风格
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

    # 创建日记记录
    now = _now_ms()
    material_ids = [m.id for m in materials]
    d = Diary(
        id=_uuid(),
        user_id=user_id,
        content=result.get("content", ""),
        title=result.get("title", "今日日记"),
        images=_encode([]),
        emotion=_encode({}),
        tags=_encode([]),
        weather=weather,
        date=date,
        material_ids=_encode(material_ids),
        emotion_summary=_encode(result.get("emotion_summary", {})),
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    # 更新用户日记数量
    if user:
        user.diary_count = (user.diary_count or 0) + 1
    db.commit()
    db.refresh(d)
    return diary_to_dict(d)


def get_emotion_trend(db: Session, user_id: str, diary_id: str) -> dict:
    """从关联素材聚合情绪趋势"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    material_ids = _decode(d.material_ids, [])
    if not material_ids:
        return {"trend": [], "dominant": ""}

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
            trend.append({
                "material_id": m.id,
                "label": em["label"],
                "score": em.get("score", 0),
                "emoji": em.get("emoji", ""),
                "created_at": m.created_at,
            })
            emotion_counts[em["label"]] = emotion_counts.get(em["label"], 0) + 1

    dominant = max(emotion_counts, key=emotion_counts.get) if emotion_counts else ""
    return {"trend": trend, "dominant": dominant}


async def extract_diary_info(db: Session, user_id: str, diary_id: str) -> dict:
    """AI 提取纪念日/人物/偏好，写入 anniversaries + user_profiles"""
    d = db.query(Diary).filter(Diary.id == diary_id, Diary.user_id == user_id).first()
    if not d:
        raise ApiException(code=NOT_FOUND, message="日记不存在", status_code=404)

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    result = await client.extract_info(d.content)

    now = _now_ms()

    # 写入纪念日
    anniversaries_created = []
    from app.models.anniversary import Anniversary
    for item in result.get("anniversaries", []):
        if item.get("title") and item.get("date"):
            ann = Anniversary(
                user_id=user_id,
                title=item["title"],
                date=item["date"],
                source="ai_extracted",
                related_person=item.get("related_person", ""),
                diary_id=diary_id,
                created_at=now,
            )
            db.add(ann)
            anniversaries_created.append(item)

    # 更新用户画像
    from app.models.user_profile import UserProfile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id, updated_at=now)
        db.add(profile)

    # 合并人物关系
    existing_relations = _decode(profile.relations, {})
    for person in result.get("persons", []):
        if person.get("name"):
            existing_relations[person["name"]] = person.get("relation", "")
    profile.relations = _encode(existing_relations)

    # 合并兴趣
    existing_interests = _decode(profile.interests, [])
    new_prefs = result.get("preferences", [])
    merged = list(set(existing_interests + new_prefs))
    profile.interests = _encode(merged)
    profile.updated_at = now

    db.commit()

    return {
        "anniversaries": anniversaries_created,
        "persons": result.get("persons", []),
        "preferences": result.get("preferences", []),
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
        # 生成漫画：调用文生图
        prompt = f"将以下日记内容绘制成温暖可爱的漫画风格插图：{d.content[:200]}"
        media_url = await client.generate_image(prompt, aspect_ratio="1:1")
    elif dtype == "novel":
        # 生成小说：调用文本生成
        messages = [{"role": "user", "content": f"将以下日记改写成有趣的短篇小说（300字）：\n\n{d.content}"}]
        content = await client.chat_completion(messages, temperature=0.9)
    elif dtype == "share_card":
        # 生成分享卡文案
        messages = [{"role": "user", "content": f"为以下日记生成一段适合朋友圈分享的文案（80字以内）：\n\n{d.content}"}]
        content = await client.chat_completion(messages, temperature=0.8)

    # 保存衍生内容
    from app.models.derivative import DiaryDerivative
    deriv = DiaryDerivative(
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

    return {
        "id": deriv.id,
        "diary_id": diary_id,
        "type": dtype,
        "content": content,
        "media_url": media_url,
        "share_scope": "private",
        "created_at": now,
    }


def get_today_summary(db: Session, user_id: str, date: str) -> dict:
    """今日概要：素材数 + 素材列表 + 是否已生成日记"""
    # 今日素材
    materials = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id, RawMaterial.date == date)
        .order_by(RawMaterial.created_at)
        .all()
    )
    from app.material.service import material_to_dict
    material_list = [material_to_dict(m) for m in materials]

    # 今日日记
    diary = (
        db.query(Diary)
        .filter(Diary.user_id == user_id, Diary.date == date)
        .first()
    )

    return {
        "date": date,
        "material_count": len(materials),
        "materials": material_list,
        "has_diary": diary is not None,
        "diary_id": diary.id if diary else None,
        "diary_status": diary.status if diary else None,
    }
