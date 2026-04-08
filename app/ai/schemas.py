# app/ai/schemas.py
from typing import Optional
from pydantic import BaseModel
from app.serializers import CamelModel   # 注意导入 CamelModel


class FortuneOut(CamelModel):
    """运势响应（自动转 camelCase）"""
    overall: int
    study: int
    social: int
    health: int
    tip: str
    lucky_color: str
    lucky_number: int


class ChatRequest(BaseModel):
    message: str
    history: list = []


class GenerateDiaryRequest(BaseModel):
    draft: str
    emotion: Optional[str] = ""
    style: Optional[str] = "日记式"


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
