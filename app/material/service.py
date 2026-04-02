"""
素材管理服务层
实现素材 CRUD 和 AI 功能业务逻辑
"""
import json
import time
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.material import RawMaterial
from app.response import ApiException, NOT_FOUND


def _now_ms() -> int:
    return int(time.time() * 1000)


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


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
    from uuid import uuid4
    material = RawMaterial(
        id=str(uuid4()),
        user_id=user_id,
        type=data["type"],
        content=data.get("content", ""),
        media_url=data.get("media_url", ""),
        thumbnail_url=data.get("thumbnail_url", ""),
        location=_encode(data.get("location", {})),
        emotion=_encode(data.get("emotion", {"label": "平静", "score": 0.5, "emoji": "😐"})),
        tags=_encode(data.get("tags", [])),
        date=data.get("date", ""),
        created_at=_now_ms(),
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material_to_dict(material)


def list_materials(db: Session, user_id: str, date: Optional[str] = None) -> List[dict]:
    """按日期查询素材列表"""
    query = db.query(RawMaterial).filter(RawMaterial.user_id == user_id)
    if date:
        query = query.filter(RawMaterial.date == date)
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
