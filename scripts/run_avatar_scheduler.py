"""
方案B：外部独立调度脚本（可由 Windows Task Scheduler / Linux cron 每 5 分钟调用一次）

设计原则：
  - 完全独立于 FastAPI 进程，不依赖 uvicorn
  - 直接操作数据库，调用 service 层函数
  - 支持并发锁（surf_lock_until）防止重复执行
  - 支持 dry-run 模式（只打印，不写入）
  - 支持只处理指定用户（--user 参数）

使用方式：
  # 正常运行（每次触发由 cron / 任务计划程序调用）
  python scripts/run_avatar_scheduler.py

  # 只调度某个用户
  python scripts/run_avatar_scheduler.py --user xu_yining

  # 演示模式（只打印计划，不执行）
  python scripts/run_avatar_scheduler.py --dry-run

Windows Task Scheduler 配置参考：
  任务名称: RijiAvatarScheduler
  触发器: 每 5 分钟重复
  操作: E:\\catalogo\\riji\\riji-backend\\venv\\Scripts\\python.exe
  参数: E:\\catalogo\\riji\\riji-backend\\scripts\\run_avatar_scheduler.py
  起始目录: E:\\catalogo\\riji\\riji-backend

Linux cron 配置参考：
  */5 * * * * /path/to/riji-backend/venv/bin/python /path/to/riji-backend/scripts/run_avatar_scheduler.py >> /var/log/riji-scheduler.log 2>&1
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.database import SessionLocal, init_db  # noqa: E402
from app.models.avatar import AvatarStatus  # noqa: E402
from app.models.user import User  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _fmt(ts_ms: int) -> str:
    if not ts_ms:
        return "未设置"
    return datetime.fromtimestamp(ts_ms / 1000, tz=TZ).strftime("%m-%d %H:%M")


def _collect_eligible_users(db, now_ms: int, target_username: str | None = None) -> list[tuple[User, AvatarStatus]]:
    """
    查询满足冲浪条件的用户：
    1. 分身已开启 (is_active = True)
    2. 未处于静默模式 (quiet_mode = False)
    3. 开启了自动匹配或自动评论
    4. next_surf_at <= now（到了冲浪窗口）
    5. 锁未占用 (surf_lock_until <= now 或者锁过期超过 10 分钟则强制清除)
    """
    query = (
        db.query(AvatarStatus, User)
        .join(User, AvatarStatus.user_id == User.id)
        .filter(
            AvatarStatus.is_active == True,   # noqa: E712
            AvatarStatus.quiet_mode == False,  # noqa: E712
        )
        .filter(
            (AvatarStatus.auto_match_enabled == True) |  # noqa: E712
            (AvatarStatus.auto_comment_enabled == True)  # noqa: E712
        )
        .filter(AvatarStatus.next_surf_at <= now_ms)
    )
    if target_username:
        query = query.filter(User.username == target_username)

    results = query.all()
    eligible = []
    for status, user in results:
        # 强制清除超时 10 分钟的幂等锁
        lock_until = status.surf_lock_until or 0
        if lock_until > now_ms and now_ms - (lock_until - 5 * 60 * 1000) > 10 * 60 * 1000:
            print(f"  [WARN] {user.username} 的锁超时 10 分钟，强制清除")
            status.surf_lock_until = 0
            db.commit()
        elif lock_until > now_ms:
            print(f"  [SKIP] {user.username} 被幂等锁保护，跳过（锁到 {_fmt(lock_until)}）")
            continue
        eligible.append((user, status))
    return eligible


def run_scheduler(dry_run: bool = False, target_username: str | None = None) -> None:
    """主调度循环：扫描所有到期用户并触发冲浪。"""
    from app.avatar.service import run_avatar_surf_for_user

    init_db()
    now_ms = _now_ms()
    now_local = datetime.fromtimestamp(now_ms / 1000, tz=TZ)

    print(f"\n{'=' * 60}")
    print(f"分身冲浪调度器启动  {now_local.strftime('%Y-%m-%d %H:%M:%S')} (Asia/Shanghai)")
    if dry_run:
        print("【DRY-RUN 模式，只打印不执行】")
    print("=" * 60)

    db = SessionLocal()
    try:
        eligible = _collect_eligible_users(db, now_ms, target_username)

        if not eligible:
            print("当前没有需要冲浪的用户（均未到达 next_surf_at 或条件不满足）")
            return

        print(f"发现 {len(eligible)} 个用户需要冲浪：")
        for user, status in eligible:
            print(f"  - {user.username:<14} next_surf_at={_fmt(status.next_surf_at or 0)}")

        print()
        success_count = 0
        skip_count = 0
        fail_count = 0

        for user, status in eligible:
            print(f"  处理: {user.username} ...", end=" ", flush=True)
            if dry_run:
                print("(dry-run，跳过执行)")
                skip_count += 1
                continue

            try:
                result = run_avatar_surf_for_user(db, user.id, trigger="scheduler")
                status_str = result.get("status", "?")
                if status_str == "success":
                    matches = result.get("generated_matches", 0)
                    print(f"[OK] success  新匹配={matches}")
                    success_count += 1
                elif status_str == "skipped":
                    reason = result.get("reason", "")
                    print(f"[--] skipped  原因: {reason}")
                    skip_count += 1
                else:
                    print(f"[??] {status_str}")
                    skip_count += 1
            except Exception as exc:
                print(f"[FAIL] {exc}")
                fail_count += 1

        print()
        print(f"调度完成 — 成功: {success_count}  跳过: {skip_count}  失败: {fail_count}")

    finally:
        db.close()

    print("=" * 60)


def print_status_report() -> None:
    """打印所有用户的冲浪状态概览（用于调试）。"""
    import json

    init_db()
    now_ms = _now_ms()
    db = SessionLocal()
    try:
        rows = (
            db.query(AvatarStatus, User)
            .join(User, AvatarStatus.user_id == User.id)
            .order_by(AvatarStatus.next_surf_at.asc())
            .all()
        )
        print(f"\n{'─' * 80}")
        print(f"{'用户名':<14} {'next_surf_at':<18} {'last_surf_at':<18} {'auto_match':<11} {'auto_comment':<13} {'confidence'}")
        print("─" * 80)
        for status, user in rows:
            try:
                plan = json.loads(status.personalized_surf_plan or "{}")
                confidence = plan.get("confidence", 0)
                bandit_count = len(plan.get("banditArms", {}))
                total_pulls = plan.get("totalPulls", 0)
            except Exception:
                confidence = 0
                bandit_count = 0
                total_pulls = 0
            overdue = "(逾期)" if (status.next_surf_at or 0) < now_ms and (status.auto_match_enabled or status.auto_comment_enabled) else ""
            print(
                f"{user.username:<14} "
                f"{_fmt(status.next_surf_at or 0):<18} "
                f"{_fmt(status.last_surf_at or 0):<18} "
                f"{'YES' if status.auto_match_enabled else 'no':<11} "
                f"{'YES' if status.auto_comment_enabled else 'no':<13} "
                f"{confidence:.2f}  bandit_arms={bandit_count}  pulls={total_pulls} {overdue}"
            )
        print("─" * 80)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="日迹分身冲浪调度器（方案B）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不执行冲浪")
    parser.add_argument("--user", type=str, default=None, help="只处理指定用户名")
    parser.add_argument("--report", action="store_true", help="打印所有用户冲浪状态概览")
    args = parser.parse_args()

    if args.report:
        print_status_report()
    else:
        run_scheduler(dry_run=args.dry_run, target_username=args.user)
