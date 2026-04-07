"""
Alembic 迁移环境配置
- 读取 app.config 的 DATABASE_URL
- 导入所有模型以支持 autogenerate
"""
import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import Base

# 导入所有模型（autogenerate 需要 Base 知道所有表）
from app.models import user, diary, chat, study, social  # noqa: F401
from app.models import material, anniversary, derivative, user_profile  # noqa: F401
from app.models import plaza, avatar  # noqa: F401

# Alembic 配置对象
config = context.config

# 设置数据库 URL（从 app.config 读取）
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 配置 Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标 metadata（用于 autogenerate）
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式运行迁移"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
