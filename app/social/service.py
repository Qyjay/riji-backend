"""
社交模块服务层
"""
import json
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
