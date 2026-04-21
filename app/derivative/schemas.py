"""
衍生内容模块 - Pydantic 模型
"""
from pydantic import BaseModel
from app.serializers import CamelModel


class ShareRequest(BaseModel):
    """修改分享范围请求体"""
    scope: str   # 'private' | 'friends' | 'public'


class DerivativeOut(CamelModel):
    """衍生内容响应（自动转 camelCase）"""
    id: str
    diary_id: str          # 前端收到 diaryId
    type: str
    content: str
    media_url: str
    share_scope: str       # 前端收到 shareScope
    created_at: int        # 前端收到 createdAt