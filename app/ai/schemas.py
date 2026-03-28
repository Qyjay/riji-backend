"""
AI 相关 Pydantic 模型（请求/响应 Schema）
"""
from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """AI 对话请求"""
    message: str
    history: list = []  # [{"role": "user"/"assistant", "content": "..."}]


class GenerateDiaryRequest(BaseModel):
    """AI 扩写日记请求"""
    draft: str                          # 日记草稿
    emotion: Optional[str] = ""        # 情绪标签
    style: Optional[str] = "日记式"    # 写作风格


class FortuneResponse(BaseModel):
    """AI 运势响应"""
    fortune: str
    score: int
    advice: str


class ComicRequest(BaseModel):
    """AI 漫画生成请求"""
    diary_content: str
    style: Optional[str] = "可爱卡通"


class ShareCardRequest(BaseModel):
    """分享卡片请求"""
    diary_id: str
    template: Optional[str] = "default"


class BgmRequest(BaseModel):
    """BGM 生成请求"""
    mood: str   # 情绪关键词


class TtsRequest(BaseModel):
    """TTS 请求"""
    text: str
    voice: Optional[str] = "male-qn-qingse"


class NovelChapterRequest(BaseModel):
    """小说章节生成请求"""
    diary_content: str
    genre: Optional[str] = "青春"
    previous_chapter: Optional[str] = ""
