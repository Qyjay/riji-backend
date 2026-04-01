"""
数据库配置
使用同步 SQLAlchemy（降低组员门槛）
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

# 创建同步数据库引擎
# SQLite 需要 check_same_thread=False 以支持多线程
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=False,  # 设置为 True 可打印 SQL 语句（调试用）
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类，所有模型继承此类
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：提供数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库：创建所有表 + uploads 目录"""
    # 导入所有模型（确保 Base 知道它们）
    from app.models import user, diary, chat, study, social  # noqa: F401
    from app.models import material, anniversary, derivative, user_profile  # noqa: F401
    from app.models import plaza, avatar  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # 创建 uploads 目录
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
