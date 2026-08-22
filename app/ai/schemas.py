# app/ai/schemas.py
from typing import Optional
from pydantic import BaseModel, Field, field_validator
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


class VoiceIntentRequest(BaseModel):
    """小 V 语音指令原话"""
    utterance: str = ""

    @field_validator("utterance", mode="before")
    @classmethod
    def strip_utterance(cls, value):
        return str(value or "").strip()


class VoiceIntentSlotsOut(CamelModel):
    """六种意图共用一组槽位，用不到的填空字符串"""
    target: str = ""
    text: str = ""
    requirement: str = ""


class VoiceIntentOut(CamelModel):
    """意图识别结果；action 恒为合法枚举，端侧照 deeplink 分发即可"""
    action: str
    confidence: float
    slots: VoiceIntentSlotsOut
    deeplink: str
    speech: str
    source: str


class LlmModelCreateRequest(BaseModel):
    """创建用户自定义聊天模型"""
    name: str
    provider_type: str = Field(alias="providerType")
    base_url: str = Field(alias="baseUrl")
    model: str
    api_key: str = Field(alias="apiKey")

    model_config = {"populate_by_name": True}

    @field_validator("name", "provider_type", "base_url", "model", "api_key", mode="before")
    @classmethod
    def strip_required(cls, value):
        return str(value or "").strip()


class LlmModelUpdateRequest(BaseModel):
    """更新用户自定义聊天模型"""
    name: Optional[str] = None
    provider_type: Optional[str] = Field(default=None, alias="providerType")
    base_url: Optional[str] = Field(default=None, alias="baseUrl")
    model: Optional[str] = None
    api_key: Optional[str] = Field(default=None, alias="apiKey")

    model_config = {"populate_by_name": True}

    @field_validator("name", "provider_type", "base_url", "model", "api_key", mode="before")
    @classmethod
    def strip_optional(cls, value):
        if value is None:
            return None
        return str(value).strip()


class LlmModelOut(CamelModel):
    """聊天模型配置响应，不返回 API Key 明文"""
    id: str
    name: str
    provider_type: str
    base_url: str
    model: str
    is_builtin: bool = False
    is_enabled: bool = True
    has_api_key: bool = False


class LlmModelListOut(CamelModel):
    items: list[LlmModelOut]
    default_chat_model_id: str = ""


class NovelChapterRequest(BaseModel):
    """小说章节生成请求"""
    diary_content: str
    genre: Optional[str] = "青春"
    previous_chapter: Optional[str] = ""
