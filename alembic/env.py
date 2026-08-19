"""
Alembic 迁移环境配置
- 读取 app.config 的 DATABASE_URL
- 导入所有模型以支持 autogenerate
"""
import sys
import os
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateColumn
from alembic import context
from alembic.ddl import base as alembic_ddl
from alembic.ddl.base import AddColumn

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import Base

# 导入所有模型（autogenerate 需要 Base 知道所有表）
from app.models import user, diary, chat, study, social  # noqa: F401
from app.models import material, anniversary, derivative, user_profile  # noqa: F401
from app.models import plaza, avatar, memory  # noqa: F401

# Alembic 配置对象
config = context.config

# 设置数据库 URL（从 app.config 读取）
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 配置 Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标 metadata（用于 autogenerate）
target_metadata = Base.metadata


@compiles(CreateColumn, "mysql")
def compile_mysql_text_default(element, compiler, **kwargs):
    """MySQL 的 TEXT/JSON 默认值必须使用表达式默认值语法。"""
    column = element.element
    server_default = column.server_default
    text_like = isinstance(
        column.type,
        (sa.Text, sa.JSON, sa.LargeBinary),
    )
    if not text_like or server_default is None:
        return compiler.visit_create_column(element, **kwargs)

    raw_default = str(server_default.arg)
    if raw_default.startswith("(") and raw_default.endswith(")"):
        return compiler.visit_create_column(element, **kwargs)

    literal = compiler.sql_compiler.render_literal_value(raw_default, sa.String())
    column.server_default = sa.DefaultClause(sa.text(f"({literal})"))
    try:
        return compiler.visit_create_column(element, **kwargs)
    finally:
        column.server_default = server_default


@compiles(AddColumn, "mysql")
def compile_mysql_add_text_column(element, compiler, **kwargs):
    """ALTER TABLE ADD COLUMN 同样使用 MySQL 文本表达式默认值。"""
    column = element.column
    server_default = column.server_default
    text_like = isinstance(
        column.type,
        (sa.Text, sa.JSON, sa.LargeBinary),
    )
    if not text_like or server_default is None:
        return "%s %s" % (
            alembic_ddl.alter_table(
                compiler,
                element.table_name,
                element.schema,
            ),
            alembic_ddl.add_column(compiler, column, **kwargs),
        )

    raw_default = str(server_default.arg)
    if raw_default.startswith("(") and raw_default.endswith(")"):
        return "%s %s" % (
            alembic_ddl.alter_table(
                compiler,
                element.table_name,
                element.schema,
            ),
            alembic_ddl.add_column(compiler, column, **kwargs),
        )

    literal = compiler.sql_compiler.render_literal_value(raw_default, sa.String())
    column.server_default = sa.DefaultClause(sa.text(f"({literal})"))
    try:
        return "%s %s" % (
            alembic_ddl.alter_table(
                compiler,
                element.table_name,
                element.schema,
            ),
            alembic_ddl.add_column(compiler, column, **kwargs),
        )
    finally:
        column.server_default = server_default


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
