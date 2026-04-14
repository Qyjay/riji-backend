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
    return _comment_to_dict(comment, current_user)


async def agent_comment(db: Session, current_user: User, post_id: str) -> dict:
    """AI 分身自动评论：根据用户画像 + 帖子内容生成评论"""
    from app.models.avatar import AvatarMemory, AvatarProfile
    from app.ai.minimax_client import get_minimax_client

    post = _get_post_or_404(db, post_id)

    if not post.allow_agent_reply:
        raise ApiException(
            code=PARAM_INVALID, message="该帖子不允许分身回复", status_code=400
        )

    # 读取用户分身画像
    profile = db.query(AvatarProfile).filter(
        AvatarProfile.user_id == current_user.id
    ).first()
    if not profile or not (profile.summary or "").strip():
        raise ApiException(
            code=PARAM_INVALID, message="请先设置分身画像", status_code=400
        )

    # 收集用户记忆作为性格补充
    memories = (
        db.query(AvatarMemory)
        .filter(AvatarMemory.user_id == current_user.id, AvatarMemory.is_active == True)  # noqa: E712
        .order_by(AvatarMemory.created_at.desc())
        .limit(20)
        .all()
    )
    memory_text = "\n".join(
        [f"- [{m.category}] {m.content}" for m in memories]
    ) if memories else "暂无"

    # 获取帖子作者信息
    post_author = db.query(User).filter(User.id == post.user_id).first()
    post_author_name = (post_author.name or post_author.username) if post_author else "某用户"

    # 调用 AI 生成评论
    system_prompt = (
        "你是一个大学生 AI 分身代理。你需要根据主人的性格画像，"
        "以主人的口吻和风格，对一条校园广场帖子写一条友善、自然的评论。\n"
        "要求：1-3 句话，像真人回复，不要暴露自己是 AI，不要过于谄媚或套话。"
    )
    user_prompt = (
        f"【我的性格画像】\n{profile.summary}\n\n"
        f"【我的记忆/兴趣】\n{memory_text}\n\n"
        f"【帖子作者】{post_author_name}\n"
        f"【帖子类型】{post.type}\n"
        f"【帖子内容】{post.content}\n\n"
        "请以我的口吻写一条评论："
    )

    client = get_minimax_client()
    reply = await client.chat_completion(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.85,
    )

    # 清理 AI 返回（去引号、多余前缀）
    reply = reply.strip().strip('"').strip("'")

    # 创建分身评论
    comment = PlazaComment(
        id=str(uuid4()),
        post_id=post_id,
        user_id=current_user.id,
        content=reply,
        is_agent=True,
        created_at=_now_ms(),
    )
    db.add(comment)
    post.comments = (post.comments or 0) + 1
    post.agent_responses = (post.agent_responses or 0) + 1
    db.commit()
    db.refresh(comment)
    return _comment_to_dict(comment, current_user)
