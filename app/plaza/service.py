"""
广场模块服务层
实现广场帖子 CRUD、点赞、评论业务逻辑
"""
import json
import time
from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.plaza import PlazaPost, PlazaComment, PostLike
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_INVALID


def _now_ms() -> int:
    return int(time.time() * 1000)


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _post_to_dict(post: PlazaPost, user: User) -> dict:
    """PlazaPost + User ORM → 响应字典"""
    return {
        "id": post.id,
        "author_id": post.user_id,
        "author_name": user.name or user.username,
        "author_avatar": user.avatar or "",
        "author_school": user.school or "",
        "author_major": user.major or "",
        "author_grade": user.grade or "",
        "type": post.type,
        "content": post.content or "",
        "images": _decode(post.images, []),
        "location": post.location or "",
        "tags": _decode(post.tags, []),
        "likes": post.likes or 0,
        "comments": post.comments or 0,
        "agent_responses": post.agent_responses or 0,
        "created_at": post.created_at,
        "is_from_agent": post.is_from_agent or False,
        "allow_agent_reply": post.allow_agent_reply if post.allow_agent_reply is not None else True,
        "school_only": post.school_only or False,
    }


def _comment_to_dict(comment: PlazaComment, user: User) -> dict:
    """PlazaComment + User ORM → 响应字典"""
    author_name = user.name or user.username
    if comment.is_agent:
        author_name = f"{author_name}的分身"

    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "author_id": comment.user_id,
        "author_name": author_name,
        "author_avatar": user.avatar or "",
        "content": comment.content or "",
        "is_agent": comment.is_agent or False,
        "created_at": comment.created_at,
    }


def _get_post_or_404(db: Session, post_id: str) -> PlazaPost:
    """获取帖子，不存在则抛 404"""
    post = db.query(PlazaPost).filter(PlazaPost.id == post_id).first()
    if not post:
        raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)
    return post


def list_posts(
    db: Session,
    current_user: User,
    channel: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    q: Optional[str] = None,
) -> dict:
    """帖子列表（分页 + 频道筛选 + 关键词搜索 + school_only 过滤）"""
    query = db.query(PlazaPost, User).join(User, PlazaPost.user_id == User.id)

    # 频道筛选
    if channel:
        query = query.filter(PlazaPost.type == channel)

    # 关键词搜索（匹配内容或标签）
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        query = query.filter(
            PlazaPost.content.ilike(keyword) | PlazaPost.tags.ilike(keyword)
        )

    # school_only 过滤：仅本校可见的帖子只对同校用户展示
    # 非 school_only 的帖子对所有人可见，school_only 的帖子要求作者与当前用户同校
    user_school = current_user.school or ""
    query = query.filter(
        (PlazaPost.school_only == False) |  # noqa: E712
        (User.school == user_school)
    )

    # 总数
    total = query.count()

    # 分页 + 排序
    offset = (page - 1) * page_size
    rows = (
        query
        .order_by(PlazaPost.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [_post_to_dict(post, user) for post, user in rows]
    return {"items": items, "total": total}


def get_post(db: Session, current_user: User, post_id: str) -> dict:
    """帖子详情"""
    row = (
        db.query(PlazaPost, User)
        .join(User, PlazaPost.user_id == User.id)
        .filter(PlazaPost.id == post_id)
        .first()
    )
    if not row:
        raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)

    post, user = row

    # school_only 权限检查
    if post.school_only and (user.school or "") != (current_user.school or ""):
        raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)

    return _post_to_dict(post, user)


def create_post(db: Session, current_user: User, data: dict) -> dict:
    """创建帖子"""
    now = _now_ms()
    post = PlazaPost(
        id=str(uuid4()),
        user_id=current_user.id,
        type=data["type"],
        content=data["content"],
        images=_encode(data.get("images", [])),
        location=data.get("location", ""),
        tags=_encode(data.get("tags", [])),
        likes=0,
        comments=0,
        agent_responses=0,
        is_from_agent=False,
        allow_agent_reply=data.get("allow_agent_reply", True),
        school_only=data.get("school_only", False),
        created_at=now,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    from app.memory.ingestion import ingest_plaza_post

    ingest_plaza_post(db, post)
    return _post_to_dict(post, current_user)


def toggle_like(db: Session, user_id: str, post_id: str) -> None:
    """点赞/取消点赞（Toggle）"""
    post = _get_post_or_404(db, post_id)

    existing = (
        db.query(PostLike)
        .filter(PostLike.post_id == post_id, PostLike.user_id == user_id)
        .first()
    )

    if existing:
        # 取消点赞
        db.delete(existing)
        post.likes = max((post.likes or 0) - 1, 0)
    else:
        # 点赞
        like = PostLike(
            id=str(uuid4()),
            post_id=post_id,
            user_id=user_id,
            created_at=_now_ms(),
        )
        db.add(like)
        post.likes = (post.likes or 0) + 1

    db.commit()


def list_comments(db: Session, post_id: str) -> List[dict]:
    """评论列表"""
    _get_post_or_404(db, post_id)

    rows = (
        db.query(PlazaComment, User)
        .join(User, PlazaComment.user_id == User.id)
        .filter(PlazaComment.post_id == post_id)
        .order_by(PlazaComment.created_at.asc())
        .all()
    )

    return [_comment_to_dict(comment, user) for comment, user in rows]


def add_comment(db: Session, current_user: User, post_id: str, data: dict) -> dict:
    """添加评论"""
    post = _get_post_or_404(db, post_id)

    is_agent = data.get("is_agent", False)

    comment = PlazaComment(
        id=str(uuid4()),
        post_id=post_id,
        user_id=current_user.id,
        content=data["content"],
        is_agent=is_agent,
        created_at=_now_ms(),
    )
    db.add(comment)

    # 帖子评论数 +1
    post.comments = (post.comments or 0) + 1

    # 分身评论时，分身响应数也 +1
    if is_agent:
        post.agent_responses = (post.agent_responses or 0) + 1

    db.commit()
    db.refresh(comment)
    from app.memory.ingestion import ingest_plaza_comment

    ingest_plaza_comment(db, comment)
    return _comment_to_dict(comment, current_user)


async def agent_comment(db: Session, current_user: User, post_id: str) -> dict:
    """兼容入口：改为生成待审批草稿，而不是直接发布公开评论。"""
    from app.avatar.service import create_plaza_comment_draft

    action = await create_plaza_comment_draft(db, current_user, post_id)
    return {
        "action": action,
        "requires_approval": True,
        "message": "已生成分身评论草稿，请先确认后再发布。",
    }
