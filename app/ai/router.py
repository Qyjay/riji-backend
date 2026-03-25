"""
AI 功能路由骨架
组员 C+D 在此基础上实现各 AI 接口
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.ai.schemas import (
    ChatRequest, GenerateDiaryRequest, ComicRequest,
    ShareCardRequest, BgmRequest, TtsRequest, NovelChapterRequest,
)
from app.response import success

router = APIRouter(prefix="/ai", tags=["AI 功能"])


@router.post("/chat", summary="AI 对话（SSE 流式）")
async def ai_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现 - 接口 D1
    AI 流式对话（Server-Sent Events）
    1. 调用 get_minimax_client().stream_chat(messages)
    2. 以 SSE 格式返回 StreamingResponse
    3. 对话记录存入 chat_messages 表
    参考：app/ai/minimax_client.py stream_chat 方法
    """
    pass


@router.post("/generate-diary", summary="AI 扩写日记")
async def generate_diary(
    req: GenerateDiaryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 D2
    根据日记草稿 AI 扩写成完整日记
    1. 构建 system_prompt（包含风格/情绪引导）
    2. 调用 get_minimax_client().chat_completion()
    3. 返回扩写后的内容
    """
    pass


@router.get("/fortune", summary="AI 今日运势")
async def get_fortune(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 D3
    生成今日 AI 运势
    1. 获取用户最近几篇日记的情绪数据
    2. 调用 AI 生成运势文字
    3. 返回运势内容、评分、建议
    """
    pass


@router.post("/comic", summary="AI 漫画生成")
async def generate_comic(
    req: ComicRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 D4
    根据日记内容生成 AI 漫画
    1. 提取日记关键场景作为图片 prompt
    2. 调用 get_minimax_client().generate_image(prompt)
    3. 返回漫画图片 URL
    """
    pass


@router.post("/share-card", summary="生成分享卡片")
async def generate_share_card(
    req: ShareCardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 D5
    生成日记分享卡片（图片）
    1. 查询日记内容
    2. 生成卡片图片
    3. 返回卡片 URL
    """
    pass


@router.post("/bgm", summary="AI 生成 BGM")
async def generate_bgm(
    req: BgmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 D6
    根据情绪生成 BGM 音乐
    1. 根据情绪映射推荐音乐关键词
    2. 调用音乐生成 API 或返回预设音乐库 URL
    3. 返回音频 URL
    """
    pass


@router.post("/tts", summary="文字转语音")
async def text_to_speech(
    req: TtsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 C 实现 - 接口 D7
    将日记文本转换为语音
    1. 调用 get_minimax_client().text_to_speech(text, voice)
    2. 将音频保存到 uploads 目录
    3. 返回音频 URL
    """
    pass


@router.post("/novel-chapter", summary="AI 小说章节")
async def generate_novel_chapter(
    req: NovelChapterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    TODO: 组员 D 实现 - 接口 D8
    根据日记内容生成小说章节
    1. 构建创意写作 prompt
    2. 调用 get_minimax_client().chat_completion()
    3. 返回小说章节文本
    """
    pass
