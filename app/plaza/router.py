"""
广场模块路由
prefix="/api/plaza", tags=["广场"]
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.response import success
from app.plaza import schemas, service
from app.plaza.schemas import PlazaPostOut, PlazaCommentOut
from app.avatar.schemas import AgentActionOut

router = APIRouter(prefix="/plaza", tags=["广场"])


def _serialize_post(d: dict) -> dict:
    """转 camelCase 输出"""
    return PlazaPostOut(**d).model_dump(by_alias=True)


def _serialize_comment(d: dict) -> dict:
    """转 camelCase 输出"""
    return PlazaCommentOut(**d).model_dump(by_alias=True)


def _serialize_action(d: dict) -> dict:
    """转 camelCase 输出"""
    return AgentActionOut(**d).model_dump(by_alias=True)


@router.get("/posts", summary="帖子列表（分页 + 频道筛选 + 搜索）")
def list_posts(
    channel: Optional[str] = Query(None, description="频道筛选：buddy/help/share/dating"),
    q: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取广场帖子列表，支持频道筛选、关键词搜索和分页"""
    result = service.list_posts(db, current_user, channel, page, page_size, q=q)
    return success({
        "items": [_serialize_post(item) for item in result["items"]],
        "total": result["total"],
    })


@router.get("/posts/{post_id}", summary="帖子详情")
def get_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取帖子详情"""
    result = service.get_post(db, current_user, post_id)
    return success(_serialize_post(result))


@router.post("/posts", summary="创建帖子")
async def create_post(
    body: schemas.CreatePostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建一条广场帖子；type 留空或传 auto 时由 AI 判定板块"""
    result = await service.create_post(db, current_user, body.model_dump())
    return success(_serialize_post(result))


@router.post("/posts/{post_id}/like", summary="点赞/取消点赞")
def like_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle 点赞：已赞则取消，未赞则点赞"""
    service.toggle_like(db, current_user.id, post_id)
    return success(None)


@router.get("/posts/{post_id}/comments", summary="评论列表")
def list_comments(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取帖子评论列表"""
    items = service.list_comments(db, post_id)
    return success([_serialize_comment(item) for item in items])


@router.get("/comments/inbox", summary="我的评论与分身评论流")
def list_my_comment_threads(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取用户本人/分身的评论，以及别人对这些评论的回复。"""
    items = service.list_my_comment_threads(db, current_user)
    return success([_serialize_comment(item) for item in items])


@router.post("/posts/{post_id}/comments", summary="添加评论")
def add_comment(
    post_id: str,
    body: schemas.AddCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """添加评论到帖子"""
    result = service.add_comment(db, current_user, post_id, body.model_dump())
    return success(_serialize_comment(result))


@router.post("/posts/{post_id}/agent-comment", summary="AI 分身评论草稿（兼容入口）")
async def agent_comment(
    post_id: str,
    body: schemas.AgentCommentRequest = schemas.AgentCommentRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧接口：现在改为生成评论草稿，需用户审批后才会真正发布。"""
    result = await service.agent_comment(db, current_user, post_id, body.parent_comment_id)
    return success({
        "action": _serialize_action(result["action"]),
        "requiresApproval": bool(result.get("requires_approval")),
        "message": result.get("message", ""),
    })
