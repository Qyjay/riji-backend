"""
社交模块路由骨架（搭子匹配 + 消息）
组员 D 负责实现
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.social.schemas import MatchRequest, MatchActionRequest, SendMessageRequest

router = APIRouter(prefix="/social", tags=["社交"])


@router.get("/matches", summary="获取搭子列表")
def list_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现 - 接口 F1
    获取当前用户的搭子列表（已接受的匹配）
    查询 matches 表，status='accepted'，user_id 或 target_id 为当前用户
    返回对方用户信息
    """
    pass


@router.post("/match-requests", summary="发起搭子匹配")
def create_match_request(
    req: MatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现 - 接口 F2
    向目标用户发起搭子匹配申请
    1. 检查是否已存在匹配请求
    2. 创建 Match 记录（status='pending'）
    3. 返回匹配记录
    """
    pass


@router.post("/match-requests/{match_id}", summary="接受或拒绝匹配")
def respond_match_request(
    match_id: str,
    req: MatchActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现
    接受或拒绝搭子匹配申请
    1. 查询 Match 记录，验证 target_id == current_user.id
    2. 根据 action 更新 status 为 'accepted' 或 'rejected'
    """
    pass


@router.get("/messages", summary="获取消息列表")
def list_messages(
    match_id: str = Query(..., description="搭子 Match ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现 - 接口 F3
    获取指定搭子对话的消息列表
    1. 验证当前用户是否是该 match 的参与方
    2. 查询 social_messages，按 timestamp ASC 排序
    """
    pass


@router.post("/messages", summary="发送消息")
def send_message(
    req: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现
    向搭子发送消息
    1. 验证 match 存在且 status='accepted'
    2. 验证当前用户是参与方
    3. 创建 SocialMessage 记录
    """
    pass
