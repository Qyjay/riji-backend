"""
广场相关数据模型
- PlazaPost: 广场帖子
- PlazaComment: 帖子评论
- PostLike: 点赞记录
"""
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.database import Base


def _uuid():
    """生成字符串 UUID"""
    return str(uuid4())


class PlazaPost(Base):
    """广场帖子表"""
    __tablename__ = "plaza_posts"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)               # buddy / help / share / dating
    content = Column(Text, nullable=False)              # 帖子正文
    images = Column(Text, default="[]")                 # JSON: string[] 图片 URL 列表
    location = Column(String, default="")               # 位置
    tags = Column(Text, default="[]")                   # JSON: string[] 话题标签
    likes = Column(Integer, default=0)                  # 点赞数
    comments = Column(Integer, default=0)               # 评论数
    agent_responses = Column(Integer, default=0)        # 分身响应数
    is_from_agent = Column(Boolean, default=False)      # 是否由分身发布
    allow_agent_reply = Column(Boolean, default=True)   # 是否允许分身回复
    school_only = Column(Boolean, default=False)        # 仅本校可见
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

    __table_args__ = (
        # 按类型查询索引
        Index("ix_plaza_posts_type", "type"),
        # 按用户查询索引
        Index("ix_plaza_posts_user_id", "user_id"),
    )


class PlazaComment(Base):
    """帖子评论表"""
    __tablename__ = "plaza_comments"

    id = Column(String, primary_key=True, default=_uuid)
    post_id = Column(String, ForeignKey("plaza_posts.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    parent_comment_id = Column(String, ForeignKey("plaza_comments.id"), nullable=True)
    content = Column(Text, nullable=False)              # 评论内容
    is_agent = Column(Boolean, default=False)           # 是否分身评论
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

    __table_args__ = (
        # 按帖子查询索引
        Index("ix_plaza_comments_post_id", "post_id"),
        # 按父评论查询索引，用于楼中楼/评论回复
        Index("ix_plaza_comments_parent_comment_id", "parent_comment_id"),
    )


class PostLike(Base):
    """点赞记录表"""
    __tablename__ = "post_likes"

    id = Column(String, primary_key=True, default=_uuid)
    post_id = Column(String, ForeignKey("plaza_posts.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(BigInteger, nullable=False)     # 毫秒时间戳

    __table_args__ = (
        # 防止重复点赞
        UniqueConstraint("post_id", "user_id", name="uq_post_like"),
    )
