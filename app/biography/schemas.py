"""
我的小传模块输出 Schema（自动 snake_case → camelCase）
"""
from typing import List, Optional

from app.serializers import CamelModel


class IllustrationOut(CamelModel):
    diary_id: str
    image_url: str
    anchor_para: int


class ChapterOut(CamelModel):
    id: str
    chapter_index: int
    title: str
    content: str
    preview: str
    word_count: int
    summary: str
    cover_image_url: str
    illustrations: List[IllustrationOut]
    date_range_start: str
    date_range_end: str
    source_material_count: int
    source_post_count: int
    status: str
    created_at: int
    updated_at: int


class ProgressOut(CamelModel):
    threshold: int
    chapter_count: int
    pending_diary_count: int
    needed_for_next: int
    can_generate: bool
    next_chapter_index: int


class BiographyOut(CamelModel):
    chapters: List[ChapterOut]
    progress: ProgressOut


class TaskOut(CamelModel):
    task_id: str
    status: str
    chapter_id: Optional[str] = None
    chapter_index: int
    error: str
    created_at: int
    updated_at: int
