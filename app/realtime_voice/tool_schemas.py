"""实时语音工具参数 Schema。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SearchPersonalMemoryArgs(StrictToolArgs):
    query: str = Field(min_length=1, max_length=500)
    source_types: Optional[list[str]] = Field(default=None, alias="sourceTypes")
    top_k: int = Field(default=4, alias="topK", ge=1, le=6)


class GetMemoryDocumentArgs(StrictToolArgs):
    document_id: str = Field(alias="documentId", min_length=1, max_length=128)


class DraftSocialMissionArgs(StrictToolArgs):
    text: str = Field(min_length=1, max_length=500)


class CreateSocialMissionDraftArgs(StrictToolArgs):
    draft_id: str = Field(alias="draftId", min_length=1, max_length=128)
    draft_hash: str = Field(alias="draftHash", min_length=16, max_length=128)


class StartSocialMissionArgs(StrictToolArgs):
    mission_id: str = Field(alias="missionId", min_length=1, max_length=128)
    confirmation_token: str = Field(
        alias="confirmationToken",
        min_length=20,
        max_length=4096,
    )


class ListSocialMissionsArgs(StrictToolArgs):
    status: Optional[str] = Field(default=None, min_length=1, max_length=40)
    limit: int = Field(default=5, ge=1, le=10)


class GetSocialMissionProgressArgs(StrictToolArgs):
    mission_id: str = Field(alias="missionId", min_length=1, max_length=128)


class OpenAppPageArgs(StrictToolArgs):
    page: Literal[
        "home",
        "chat",
        "social",
        "social_find",
        "mission",
        "diary",
        "avatar_memory",
    ]
    resource_id: Optional[str] = Field(
        default=None,
        alias="resourceId",
        min_length=1,
        max_length=128,
    )
