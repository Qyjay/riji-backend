"""
素材管理服务层
实现素材 CRUD 和 AI 功能业务逻辑
"""
import json
import time
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.material import RawMaterial
from app.response import ApiException, NOT_FOUND


def _now_ms() -> int:
    return int(time.time() * 1000)


def _now_dt() -> datetime:
    return datetime.now()


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _resolve_date_part(date_hint: Optional[str], now_dt: datetime) -> str:
    """优先沿用传入的 YYYY-MM-DD；无效时回退到当前日期。"""
    if isinstance(date_hint, str):
        raw = date_hint.strip()
        if len(raw) >= 10:
            candidate = raw[:10]
            try:
                datetime.strptime(candidate, "%Y-%m-%d")
                return candidate
            except ValueError:
                pass
    return now_dt.strftime("%Y-%m-%d")


def _build_material_date(date_hint: Optional[str], now_dt: datetime) -> str:
    """生成素材日期（精确到秒）。"""
    date_part = _resolve_date_part(date_hint, now_dt)
    return f"{date_part} {now_dt.strftime('%H:%M:%S')}"


def _build_base_material_id(user_id: str, now_dt: datetime) -> str:
    """按 年月日时分秒+用户ID 生成主键基础串。"""
    return f"{now_dt.strftime('%Y%m%d%H%M%S')}_{user_id}"


def _build_unique_material_id(db: Session, user_id: str, now_dt: datetime) -> str:
    """在同秒并发或快速连续写入时，避免主键冲突。"""
    base_id = _build_base_material_id(user_id, now_dt)
    candidate_id = base_id
    suffix = 1
    while db.query(RawMaterial.id).filter(RawMaterial.id == candidate_id).first():
        candidate_id = f"{base_id}_{suffix}"
        suffix += 1
    return candidate_id


def _same_payload(last: RawMaterial, payload: dict) -> bool:
    """判断两条素材是否为同一请求负载，用于防抖去重。"""
    return (
        (last.type or "") == payload["type"]
        and (last.content or "") == payload["content"]
        and (last.media_url or "") == payload["media_url"]
        and (last.thumbnail_url or "") == payload["thumbnail_url"]
        and _decode(last.location, {}) == payload["location"]
    )


def _normalize_create_payload(data: dict) -> dict:
    default_emotion = {"label": "平静", "score": 0.5, "emoji": "😐"}
    payload = {
        "type": data["type"],
        "content": data.get("content", "") or "",
        "media_url": data.get("media_url", "") or "",
        "thumbnail_url": data.get("thumbnail_url", "") or "",
        "location": data.get("location", {}) or {},
        "emotion": data.get("emotion") or default_emotion,
        "tags": data.get("tags", []) or [],
    }

    media_url = payload["media_url"]
    if media_url and (not payload["thumbnail_url"] or not payload["location"]):
        from app.upload.service import get_uploaded_image_meta

        uploaded_meta = get_uploaded_image_meta(media_url)
        if uploaded_meta:
            if not payload["thumbnail_url"]:
                payload["thumbnail_url"] = uploaded_meta.get("thumbnail_url", "")
            if not payload["location"]:
                payload["location"] = uploaded_meta.get("location", {}) or {}

    return payload


def _apply_material_date_filter(query, date: Optional[str]):
    """兼容按天查询（YYYY-MM-DD）与精确到秒查询。"""
    if not date:
        return query

    date_value = date.strip()
    if len(date_value) == 10:
        return query.filter(RawMaterial.date.like(f"{date_value}%"))
    return query.filter(RawMaterial.date == date_value)


def material_to_dict(m: RawMaterial) -> dict:
    """素材模型转响应字典"""
    return {
        "id": m.id,
        "user_id": m.user_id,
        "type": m.type,
        "content": m.content or "",
        "media_url": m.media_url or "",
        "thumbnail_url": m.thumbnail_url or "",
        "location": _decode(m.location, {}),
        "emotion": _decode(m.emotion, {"label": "平静", "score": 0.5, "emoji": "😐"}),
        "tags": _decode(m.tags, []),
        "date": m.date or "",
        "created_at": m.created_at,
        # chat 类型专属字段
        "chat_session_id": m.chat_session_id or None,
        "start_time": m.start_time or None,
        "end_time": m.end_time or None,
    }


def create_material(db: Session, user_id: str, data: dict) -> dict:
    """创建素材"""
    now_ms = _now_ms()
    now_dt = _now_dt()
    payload = _normalize_create_payload(data)

    latest = (
        db.query(RawMaterial)
        .filter(RawMaterial.user_id == user_id)
        .order_by(RawMaterial.created_at.desc())
        .first()
    )

    if latest and latest.created_at and (now_ms - latest.created_at) < 1000:
        if _same_payload(latest, payload):
            return material_to_dict(latest)

    material = RawMaterial(
        id=_build_unique_material_id(db, user_id, now_dt),
        user_id=user_id,
        type=payload["type"],
        content=payload["content"],
        media_url=payload["media_url"],
        thumbnail_url=payload["thumbnail_url"],
        location=_encode(payload["location"]),
        emotion=_encode(payload["emotion"]),
        tags=_encode(payload["tags"]),
        date=_build_material_date(data.get("date"), now_dt),
        created_at=now_ms,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material_to_dict(material)


def list_materials(db: Session, user_id: str, date: Optional[str] = None) -> List[dict]:
    """按日期查询素材列表"""
    query = db.query(RawMaterial).filter(RawMaterial.user_id == user_id)
    query = _apply_material_date_filter(query, date)
    materials = query.order_by(RawMaterial.created_at.asc()).all()
    return [material_to_dict(m) for m in materials]


def get_material(db: Session, user_id: str, material_id: str) -> dict:
    """获取单条素材详情"""
    m = db.query(RawMaterial).filter(
        RawMaterial.id == material_id,
        RawMaterial.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="素材不存在", status_code=404)
    return material_to_dict(m)


def update_material(db: Session, user_id: str, material_id: str, data: dict) -> dict:
    """更新素材字段"""
    m = db.query(RawMaterial).filter(
        RawMaterial.id == material_id,
        RawMaterial.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="素材不存在", status_code=404)

    if "content" in data and data["content"] is not None:
        m.content = data["content"]
    if "media_url" in data and data["media_url"] is not None:
        m.media_url = data["media_url"]
    if "thumbnail_url" in data and data["thumbnail_url"] is not None:
        m.thumbnail_url = data["thumbnail_url"]
    if "location" in data and data["location"] is not None:
        m.location = _encode(data["location"])
    if "emotion" in data and data["emotion"] is not None:
        m.emotion = _encode(data["emotion"])
    if "tags" in data and data["tags"] is not None:
        m.tags = _encode(data["tags"])

    db.commit()
    db.refresh(m)
    return material_to_dict(m)


def delete_material(db: Session, user_id: str, material_id: str) -> None:
    """删除素材"""
    m = db.query(RawMaterial).filter(
        RawMaterial.id == material_id,
        RawMaterial.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="素材不存在", status_code=404)
    db.delete(m)
    db.commit()


async def extract_emotion(db: Session, user_id: str, material_id: str) -> dict:
    """AI 情绪提取，结果写回数据库"""
    m = db.query(RawMaterial).filter(
        RawMaterial.id == material_id,
        RawMaterial.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="素材不存在", status_code=404)

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    emotion = await client.extract_emotion(m.content or "")

    m.emotion = _encode(emotion)
    db.commit()
    db.refresh(m)
    return emotion


async def polish_text(db: Session, user_id: str, material_id: str, style: str) -> dict:
    """AI 文字润色，只返回 {polished}"""
    m = db.query(RawMaterial).filter(
        RawMaterial.id == material_id,
        RawMaterial.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="素材不存在", status_code=404)

    from app.ai.minimax_client import get_minimax_client
    client = get_minimax_client()
    polished = await client.polish_text(m.content or "", style)

    return {"polished": polished}
