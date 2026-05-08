"""
社交模块服务层
"""
import json
import time
from uuid import uuid4
from typing import Optional

from sqlalchemy.orm import Session

from app.ai.minimax_client import get_minimax_client
from app.models.social import Match, SocialMessage
from app.models.user import User
from app.models.user_profile import UserProfile
from app.response import ApiException, NOT_FOUND, PARAM_ERROR


def _encode(obj, default="") -> str:
    if obj is None:
        return default
    return json.dumps(obj, ensure_ascii=False)


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
        "status": match.status or "pending",
        "match_type": match.match_type or "long_term",
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


def _uuid() -> str:
    return str(uuid4())


def _get_match(db: Session, match_id: str) -> Optional[Match]:
    return db.query(Match).filter(Match.id == match_id).first()


def _get_match_for_user(db: Session, match_id: str, user_id: str) -> Match:
    match = _get_match(db, match_id)
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    if match.user_id != user_id and match.target_id != user_id:
        raise ApiException(code=NOT_FOUND, message="匹配不存在", status_code=404)
    return match


def _profile_to_dict(profile: Optional[UserProfile]) -> dict:
    if not profile:
        return {}
    return {
        "personality": profile.personality or "",
        "interests": _decode(profile.interests, []),
    }


def _avatar_card_to_dict(card) -> dict:
    if not card:
        return {}
    return {
        "display_name": card.display_name or "",
        "public_summary": card.public_summary or "",
        "interest_tags": _decode(card.interest_tags, []),
        "social_intent": _decode(card.social_intent, []),
        "conversation_style": _decode(card.conversation_style, {}),
        "boundaries": _decode(card.boundaries, []),
    }


def _normalize_match_report(report_data: dict) -> dict:
    return {
        "compatibility": report_data.get("compatibility", 75),
        "analysis": report_data.get("analysis", ""),
        "common_points": report_data.get("common_points", report_data.get("commonPoints", [])),
        "differences": report_data.get("differences", []),
    }


def list_matches(db: Session, user_id: str, include_pending: bool = False) -> list[dict]:
    """查询匹配列表；默认仅已接受（与历史行为一致）。include_pending=True 时包含 pending，便于核对搭子申请。"""
    q = db.query(Match).filter(
        (Match.user_id == user_id) | (Match.target_id == user_id),
    )
    if include_pending:
        q = q.filter(Match.status.in_(["accepted", "pending"]))
    else:
        q = q.filter(Match.status == "accepted")
    matches = q.order_by(Match.created_at.desc()).all()
    return [match_to_out(match, user_id, db) for match in matches]


def create_match_request(db: Session, user_id: str, target_uid: Optional[str]) -> Match:
    """创建长期匹配请求"""
    if not target_uid:
        raise ApiException(code=PARAM_ERROR, message="toUid 不能为空", status_code=400)

    target = db.query(User).filter(User.id == target_uid).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    existing = db.query(Match).filter(
        ((Match.user_id == user_id) & (Match.target_id == target_uid))
        | ((Match.user_id == target_uid) & (Match.target_id == user_id))
    ).first()
    if existing:
        raise ApiException(code=PARAM_ERROR, message="已存在匹配请求", status_code=400)

    match = Match(
        id=_uuid(),
        user_id=user_id,
        target_id=target_uid,
        common_tags=_encode([], "[]"),
        status="pending",
        match_type="long_term",
        created_at=_now_ms(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def get_messages(
    db: Session,
    user_id: str,
    match_id: str,
    limit: int = 50,
    before: Optional[str] = None,
) -> list[SocialMessage]:
    """获取指定匹配的聊天记录"""
    _get_match_for_user(db, match_id, user_id)

    query = db.query(SocialMessage).filter(SocialMessage.match_id == match_id)
    if before:
        pivot = db.query(SocialMessage).filter(SocialMessage.id == before).first()
        if pivot:
            query = query.filter(SocialMessage.timestamp < pivot.timestamp)

    return query.order_by(SocialMessage.timestamp.desc()).limit(limit).all()


def send_message(db: Session, user_id: str, match_id: str, content: str) -> SocialMessage:
    """发送社交消息，要求匹配已接受且当前用户属于该匹配"""
    match = _get_match_for_user(db, match_id, user_id)
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
    from app.memory.ingestion import ingest_social_message

    ingest_social_message(db, message)
    return message


async def get_match_report(db: Session, user_id: str, match_id: str) -> dict:
    """获取或生成匹配报告"""
    match = _get_match_for_user(db, match_id, user_id)

    if match.match_report:
        try:
            cached = json.loads(match.match_report)
            if isinstance(cached, dict) and "compatibility" in cached:
                return _normalize_match_report(cached)
        except Exception:
            pass

    client = get_minimax_client()
    other_id = get_other_user_id(match, user_id)
    profile_a = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    profile_b = db.query(UserProfile).filter(UserProfile.user_id == other_id).first()
    from app.models.memory import AvatarCard

    card_a = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    card_b = db.query(AvatarCard).filter(AvatarCard.user_id == other_id).first()
    portrait_a = _profile_to_dict(profile_a)
    portrait_b = _profile_to_dict(profile_b)
    if card_a:
        portrait_a["avatar_card"] = _avatar_card_to_dict(card_a)
    if card_b:
        portrait_b["avatar_card"] = _avatar_card_to_dict(card_b)

    if client.mock:
        report_data = {
            "compatibility": 85,
            "analysis": "你们有很多共同点，在学习和生活方式上非常契合！",
            "common_points": ["都喜欢记录生活", "学习态度积极", "兴趣爱好相近"],
            "differences": ["作息时间略有差异", "对社交的需求程度不同"],
        }
    else:
        try:
            raw_report = await client.generate_match_report(
                portrait_a,
                portrait_b,
            )
            import re

            json_match = re.search(r"\{.*\}", raw_report, re.DOTALL)
            if json_match:
                report_data = json.loads(json_match.group())
            else:
                report_data = {
                    "compatibility": 75,
                    "analysis": raw_report[:200] if raw_report else "匹配度较高，有共同语言。",
                    "common_points": ["有共同兴趣"],
                    "differences": ["性格略有差异"],
                }
        except Exception:
            report_data = {
                "compatibility": 85,
                "analysis": "你们有很多共同点，在学习和生活方式上非常契合！",
                "common_points": ["都喜欢记录生活", "学习态度积极", "兴趣爱好相近"],
                "differences": ["作息时间略有差异", "对社交的需求程度不同"],
            }

    normalized_report = _normalize_match_report(report_data)
    match.match_report = _encode(normalized_report, "{}")
    db.commit()
    return normalized_report


def respond_match_request(db: Session, user_id: str, request_id: str, accept: bool) -> None:
    """接受或拒绝匹配申请"""
    match = db.query(Match).filter(Match.id == request_id, Match.target_id == user_id).first()
    if not match:
        raise ApiException(code=NOT_FOUND, message="匹配请求不存在", status_code=404)

    match.status = "accepted" if accept else "rejected"
    db.commit()


def apply_buddy(db: Session, user_id: str, target_user_id: str, reason: str = "") -> Match:
    """发起短期搭子申请"""
    target = db.query(User).filter(User.id == target_user_id).first()
    if not target:
        raise ApiException(code=NOT_FOUND, message="用户不存在", status_code=404)

    match = Match(
        id=_uuid(),
        user_id=user_id,
        target_id=target_user_id,
        common_tags=_encode([], "[]"),
        status="pending",
        match_type="buddy",
        match_report=reason,
        created_at=_now_ms(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def respond_buddy(db: Session, user_id: str, request_id: str, accept: bool) -> None:
    """同意或拒绝搭子申请（仅接收方 target_id 可操作，与 POST /social/buddy 发起方向一致）"""
    match = db.query(Match).filter(
        Match.id == request_id,
        Match.match_type == "buddy",
    ).first()
    if not match:
        raise ApiException(
            code=NOT_FOUND,
            message="搭子申请不存在：请确认路径里的 id 是「分身 start-chat」或「申请搭子」接口返回的 social 匹配 id，而不是分身推荐 AvatarMatch 的 id",
            status_code=404,
        )
    if match.target_id != user_id:
        if match.user_id == user_id:
            raise ApiException(
                code=PARAM_INVALID,
                message="你是该搭子申请的发起方，不能给自己执行同意/拒绝；请让对方（接收方）登录后调用本接口",
                status_code=400,
            )
        raise ApiException(
            code=NOT_FOUND,
            message="搭子申请不存在或当前登录用户不是该申请的接收方；请用接收方账号（密码见种子数据说明）登录后再试",
            status_code=404,
        )

    if match.status != "pending":
        raise ApiException(code=PARAM_INVALID, message="该搭子申请已处理，无需再次响应", status_code=400)

    match.status = "accepted" if accept else "rejected"

    # 同步关联的 AtoaInteraction.outcome（Phase 8C 社交闭环）
    try:
        from app.models.avatar import AvatarAtoaInteraction
        interaction = (
            db.query(AvatarAtoaInteraction)
            .filter(AvatarAtoaInteraction.triggered_match_id == match.id)
            .first()
        )
        if interaction and interaction.outcome == "connected":
            import time as _time
            interaction.outcome = "connect_confirmed" if accept else "connect_rejected"
            interaction.updated_at = int(_time.time() * 1000)
    except Exception:
        pass  # 不影响主流程

    db.commit()
