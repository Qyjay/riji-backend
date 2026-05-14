"""
数据库配置
使用同步 SQLAlchemy（降低组员门槛）
"""
import os
from sqlalchemy import String, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings


@compiles(String, "mysql")
def _compile_mysql_string(element, compiler, **kwargs):
    """MySQL requires VARCHAR length; SQLite allowed the existing bare String."""
    if element.length is None:
        return "VARCHAR(255)"
    return compiler.visit_VARCHAR(element, **kwargs)


def _sqlite_connect_args(database_url: str) -> dict:
    if "sqlite" not in database_url:
        return {}
    return {
        "check_same_thread": False,
        "timeout": 30,
    }


def _engine_kwargs(database_url: str) -> dict:
    kwargs = {
        "connect_args": _sqlite_connect_args(database_url),
        "echo": False,  # 设置为 True 可打印 SQL 语句（调试用）
    }
    if "mysql" in database_url:
        kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_recycle": 1800,
            }
        )
    return kwargs


# 创建同步数据库引擎
# SQLite 需要 check_same_thread=False 以支持多线程
engine = create_engine(
    settings.DATABASE_URL,
    **_engine_kwargs(settings.DATABASE_URL),
)


if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


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
    from app.models import plaza, avatar, memory  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # 创建 uploads 目录
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
