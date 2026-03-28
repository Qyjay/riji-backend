"""
聊天模块 Pydantic Schema（组员 D 根据需要扩展）
"""
from pydantic import BaseModel


class GetHistoryRequest(BaseModel):
    """获取历史消息请求"""
    limit: int = 50
    before_timestamp: int = 0  # 获取此时间戳之前的消息（翻页用）
