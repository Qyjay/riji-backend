"""记忆系统 API schemas。"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.serializers import CamelModel


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str = ""
    scenario: str = "chat"
    top_k: int = Field(default=6, alias="topK", ge=1, le=30)
    source_types: Optional[List[str]] = Field(default=None, alias="sourceTypes")


class MemorySearchItem(CamelModel):
    document_id: str
    chunk_id: str
    source_type: str
    source_id: str
    title: str
    content: str
    visibility: str
    score: float
    occurred_at: int


class MemoryDocumentOut(CamelModel):
    id: str
    source_type: str
    source_id: str
    title: str
    content: str
    summary: str
    visibility: str
    memory_scope: str
    occurred_at: int
    created_at: int
    updated_at: int
    tags: list = []


class MemoryFactOut(CamelModel):
    id: str
    category: str
    content: str
    subject: str = ""
    predicate: str = ""
    object: str = ""
    confidence: float = 0.0
    stability: str = ""
    is_active: bool = True
    is_pinned: bool = False
    created_at: int
    updated_at: int


class CreateMemoryFactRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category: str = "profile"
    content: str
    subject: str = "user"
    predicate: str = "has_fact"
    object: str = ""
    confidence: float = Field(default=1.0, ge=0, le=1)
    stability: str = "stable"
    is_pinned: bool = Field(default=False, alias="isPinned")


class MemoryProfileOut(CamelModel):
    id: str
    profile_type: str
    summary: str
    traits: dict
    interests: list
    preferences: dict
    relations: dict
    social_style: dict
    boundaries: list
    recent_state: str
    version: int
    generated_at: int
    source_range: dict


class UpdateMemoryFactRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    content: Optional[str] = None
    is_active: Optional[bool] = Field(default=None, alias="isActive")
    is_pinned: Optional[bool] = Field(default=None, alias="isPinned")
    category: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class AgentContextRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    owner_user_id: str = Field(alias="ownerUserId")
    query: str = ""
    top_k: int = Field(default=5, alias="topK", ge=1, le=20)


class DecayMemoryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    older_than_days: int = Field(default=180, alias="olderThanDays", ge=1)
    decay_factor: float = Field(default=0.92, alias="decayFactor", gt=0, le=1)
    min_confidence: float = Field(default=0.3, alias="minConfidence", ge=0, le=1)
