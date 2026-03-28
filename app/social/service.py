"""
社交模块服务层
"""
import json
import time
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.models.social import Match, SocialMessage
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_ERROR


def _decode(s, default=None):
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def get_other_user_id(match: Match, current_user_id: str) -> str:
    """获取对方用户 ID"""
    return match.target_id if match.user_id == current_user_id else match.user_id


def match_to_out(match: Match, current_user_id: str, db: Session) -> dict:
    """匹配记录转前端格式（需要 JOIN 用户信息）"""
    other_id = get_other_user_id(match, current_user_id)
    other_user = db.query(User).filter(User.id == other_id).first()

    return {
        "id": match.id,
        "nickname": other_user.name or other_user.username if other_user else "",
        "avatar": other_user.avatar or "" if other_user else "",
        "school": other_user.school or "" if other_user else "",
        "common_tags": _decode(match.common_tags, []),
        "matched_at": match.created_at,
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def send_message(db: Session, user_id: str, match_id: str, content: str) -> SocialMessage:
    """发送社交消息，要求匹配已接受且当前用户属于该匹配"""
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    if match.user_id != user_id and match.target_id != user_id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)

    if match.status != "accepted":
        raise ApiException(code=PARAM_ERROR, message="匹配未通过，暂时不能发送消息", status_code=400)

    clean_content = content.strip()
    if not clean_content:
        raise ApiException(code=PARAM_ERROR, message="消息内容不能为空", status_code=400)

    message = SocialMessage(
        id=_uuid(),
        match_id=match_id,
        from_uid=user_id,
        content=clean_content,
        timestamp=_now_ms(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
