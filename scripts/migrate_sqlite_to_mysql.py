#!/usr/bin/env python3
"""Copy all application tables from SQLite to MySQL.

The script is intentionally conservative:
- it creates the target schema from SQLAlchemy models;
- it refuses to write into a non-empty target unless --overwrite-target is used;
- it verifies source/target row counts after copying;
- it stamps alembic_version to the current migration head so container startup
  does not replay SQLite-era migrations on the freshly created MySQL schema.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402


SKIP_TABLES = {"alembic_version"}


def _sqlite_url(path_or_url: str) -> str:
    raw = str(path_or_url or "").strip()
    if raw.startswith("sqlite:"):
        return raw
    return f"sqlite:///{Path(raw).expanduser().resolve().as_posix()}"


def _make_engine(url: str) -> Engine:
    kwargs = {"pool_pre_ping": True} if "mysql" in url else {}
    return create_engine(url, **kwargs)


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _count_rows(engine: Engine, table_name: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar() or 0)


def _target_has_data(engine: Engine, table_names: Iterable[str]) -> bool:
    existing = _table_names(engine)
    for table_name in table_names:
        if table_name in SKIP_TABLES or table_name not in existing:
            continue
        if _count_rows(engine, table_name) > 0:
            return True
    return False


def _set_mysql_foreign_key_checks(conn, enabled: bool) -> None:
    if conn.dialect.name == "mysql":
        conn.execute(text(f"SET FOREIGN_KEY_CHECKS={1 if enabled else 0}"))


def _stamp_alembic_head(target_engine: Engine) -> str:
    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    head = script.get_current_head()
    if not head:
        raise RuntimeError("Cannot determine Alembic head revision")

    with target_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
            {"version_num": head},
        )
    return head


def migrate(source_url: str, target_url: str, overwrite_target: bool, batch_size: int) -> None:
    source_engine = _make_engine(source_url)
    target_engine = _make_engine(target_url)

    source_tables = _table_names(source_engine)
    ordered_tables = [table for table in Base.metadata.sorted_tables if table.name in source_tables]
    ordered_names = [table.name for table in ordered_tables if table.name not in SKIP_TABLES]

    print(f"Source tables: {len(source_tables)}")
    print(f"Application tables to copy: {len(ordered_names)}")

    Base.metadata.create_all(bind=target_engine)

    if _target_has_data(target_engine, ordered_names):
        if not overwrite_target:
            raise SystemExit(
                "Target database already has data. Refusing to continue. "
                "Use --overwrite-target only after taking a backup."
            )
        with target_engine.begin() as conn:
            _set_mysql_foreign_key_checks(conn, False)
            for table in reversed(ordered_tables):
                if table.name not in SKIP_TABLES:
                    conn.execute(delete(table))
            _set_mysql_foreign_key_checks(conn, True)

    source_meta = MetaData()
    source_meta.reflect(bind=source_engine, only=ordered_names)

    copied_counts: dict[str, int] = {}
    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        _set_mysql_foreign_key_checks(target_conn, False)
        for target_table in ordered_tables:
            table_name = target_table.name
            if table_name in SKIP_TABLES:
                continue

            source_table = source_meta.tables[table_name]
            result = source_conn.execute(select(source_table))
            copied = 0
            while True:
                rows = result.mappings().fetchmany(batch_size)
                if not rows:
                    break
                payload = [dict(row) for row in rows]
                target_conn.execute(target_table.insert(), payload)
                copied += len(payload)
            copied_counts[table_name] = copied
            print(f"Copied {table_name}: {copied}")
        _set_mysql_foreign_key_checks(target_conn, True)

    failures = []
    for table_name, copied in copied_counts.items():
        target_count = _count_rows(target_engine, table_name)
        if target_count != copied:
            failures.append((table_name, copied, target_count))

    if failures:
        for table_name, source_count, target_count in failures:
            print(
                f"Count mismatch for {table_name}: "
                f"source={source_count} target={target_count}",
                file=sys.stderr,
            )
        raise SystemExit(1)

    head = _stamp_alembic_head(target_engine)
    print(f"Stamped alembic_version: {head}")
    print("Migration completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate riji backend data from SQLite to MySQL.")
    parser.add_argument(
        "--source",
        default=os.getenv("SQLITE_DATABASE_URL") or "./data.db",
        help="SQLite file path or sqlite:/// URL. Defaults to ./data.db.",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("MYSQL_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="MySQL SQLAlchemy URL, for example mysql+pymysql://user:pass@127.0.0.1:3306/riji?charset=utf8mb4.",
    )
    parser.add_argument(
        "--overwrite-target",
        action="store_true",
        help="Delete existing target application table data before copying. Use only after backup.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    if not args.target or not str(args.target).startswith("mysql"):
        raise SystemExit("--target or MYSQL_DATABASE_URL must be a mysql+pymysql:// URL")

    migrate(
        source_url=_sqlite_url(args.source),
        target_url=args.target,
        overwrite_target=args.overwrite_target,
        batch_size=max(args.batch_size, 1),
    )


if __name__ == "__main__":
    main()
