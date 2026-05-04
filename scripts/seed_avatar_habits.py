"""
为 10 个真实测试用户注入 App 使用习惯数据（AvatarUsageStat）。

脚本行为：
- 根据每个用户的人设，写入「按星期 × 小时」聚合的使用习惯统计
- 将所有用户的分身状态设置为 auto_match_enabled=True、surf_frequency="adaptive"
- 调用 _compute_personalized_surf_plan 生成个性化计划并写回 avatar_status
- 写入若干历史 AvatarSurfLog，模拟系统已经运行过几次冲浪

运行方式（在项目根目录）：
    python scripts/seed_avatar_habits.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.database import SessionLocal, init_db  # noqa: E402
from app.models.avatar import (  # noqa: E402
    AvatarStatus,
    AvatarSurfLog,
    AvatarUsageStat,
)
from app.models.user import User  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")


def _ms(dt_text: str) -> int:
    dt = datetime.strptime(dt_text, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    return int(dt.timestamp() * 1000)


def _encode(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _now_ms() -> int:
    return int(datetime.now(TZ).timestamp() * 1000)


# ─────────────────────────────────────────────
# 每个用户的「特征使用时段」
# 格式: [(weekday, hour, open_count, active_minutes, page_weights)]
#   weekday: 0=周一 … 6=周日
#   open_count: 该小时累计打开/回到前台次数（11天合计）
#   active_minutes: 该小时累计活跃分钟数（11天合计）
#   page_weights: 常用页面分布
# ─────────────────────────────────────────────
USAGE_PROFILES: dict[str, list[tuple[int, int, int, int, dict]]] = {
    # 许以宁 — 软件工程，晚间刷题复盘，偶尔午间
    "xu_yining": [
        (0, 21, 9, 48, {"diary": 5, "chat": 3, "plaza": 1}),
        (1, 21, 8, 42, {"diary": 4, "chat": 4}),
        (2, 21, 10, 55, {"chat": 5, "diary": 4, "plaza": 1}),
        (3, 21, 9, 50, {"diary": 5, "chat": 3}),
        (4, 20, 7, 35, {"plaza": 4, "diary": 2, "chat": 1}),
        (5, 20, 6, 28, {"avatar": 3, "diary": 2, "chat": 1}),
        (6, 21, 8, 44, {"diary": 5, "chat": 3}),
        (0, 22, 5, 22, {"chat": 3, "diary": 2}),
        (2, 9,  3, 12, {"plaza": 2, "diary": 1}),
        (4, 15, 4, 18, {"diary": 3, "chat": 1}),
    ],
    # 乔盟 — 建筑学，创作下午 + 社交晚间
    "qiao_meng": [
        (0, 14, 7, 38, {"plaza": 5, "diary": 2}),
        (1, 15, 8, 42, {"plaza": 4, "diary": 3, "chat": 1}),
        (2, 14, 6, 30, {"plaza": 4, "avatar": 2}),
        (3, 15, 7, 35, {"diary": 4, "plaza": 3}),
        (4, 14, 8, 40, {"plaza": 5, "diary": 3}),
        (5, 20, 9, 50, {"diary": 5, "chat": 4, "plaza": 2}),
        (6, 21, 8, 45, {"chat": 4, "diary": 4, "plaza": 2}),
        (0, 20, 5, 25, {"chat": 3, "diary": 2}),
        (3, 20, 6, 30, {"plaza": 3, "chat": 2}),
    ],
    # 苏雯 — 临床医学，深夜交班后 + 早晨快速浏览
    "su_wen": [
        (0, 22, 8, 35, {"diary": 5, "chat": 3}),
        (1, 22, 9, 42, {"chat": 5, "diary": 4}),
        (2, 23, 6, 28, {"diary": 4, "chat": 2}),
        (3, 22, 8, 38, {"diary": 4, "chat": 4}),
        (4, 23, 7, 32, {"chat": 4, "diary": 3}),
        (5, 7,  5, 18, {"diary": 3, "plaza": 2}),
        (6, 8,  6, 22, {"plaza": 3, "diary": 3, "chat": 1}),
        (0, 7,  3, 10, {"diary": 2, "plaza": 1}),
        (2, 22, 5, 20, {"chat": 3, "diary": 2}),
        (4, 7,  4, 15, {"diary": 3}),
    ],
    # 贺卓 — 法学，下午图书馆 + 晚间结构化复盘
    "he_zhuo": [
        (0, 15, 7, 40, {"diary": 5, "chat": 2}),
        (1, 14, 8, 45, {"diary": 4, "chat": 3, "plaza": 1}),
        (2, 15, 6, 32, {"chat": 4, "diary": 3}),
        (3, 16, 7, 38, {"diary": 4, "plaza": 2, "chat": 2}),
        (4, 15, 6, 30, {"chat": 4, "diary": 2}),
        (5, 21, 8, 42, {"diary": 5, "chat": 3}),
        (6, 21, 9, 48, {"chat": 5, "diary": 4}),
        (0, 21, 6, 28, {"diary": 3, "chat": 3}),
        (3, 21, 7, 35, {"diary": 4, "plaza": 2}),
        (1, 16, 4, 18, {"plaza": 3, "chat": 1}),
    ],
    # 林瑶 — 新闻传播，全时段高活跃，早晨创作 + 晚间社交
    "lin_yao": [
        (0, 9,  10, 55, {"plaza": 6, "diary": 3, "chat": 2}),
        (1, 9,  11, 60, {"plaza": 7, "chat": 3, "diary": 2}),
        (2, 10, 9,  50, {"plaza": 5, "diary": 4, "avatar": 2}),
        (3, 9,  10, 55, {"plaza": 6, "chat": 3, "diary": 2}),
        (4, 10, 8,  45, {"plaza": 5, "diary": 3, "chat": 2}),
        (5, 20, 10, 58, {"plaza": 6, "chat": 4, "diary": 2}),
        (6, 21, 11, 62, {"chat": 6, "plaza": 4, "diary": 2}),
        (1, 20, 7,  38, {"plaza": 4, "chat": 3}),
        (3, 20, 8,  42, {"chat": 4, "plaza": 3, "diary": 1}),
        (5, 11, 5,  25, {"diary": 3, "plaza": 2}),
    ],
    # 江南溪 — 工业设计，创意上午 + 设计审查傍晚
    "jiang_nanxi": [
        (0, 10, 8, 42, {"diary": 5, "chat": 3, "plaza": 1}),
        (1, 11, 7, 38, {"diary": 4, "plaza": 3}),
        (2, 10, 9, 48, {"chat": 5, "diary": 4}),
        (3, 10, 8, 40, {"diary": 4, "plaza": 3, "avatar": 1}),
        (4, 11, 7, 36, {"diary": 3, "chat": 3, "plaza": 2}),
        (5, 19, 8, 44, {"diary": 5, "chat": 3}),
        (6, 20, 9, 50, {"chat": 5, "diary": 4, "plaza": 1}),
        (1, 19, 5, 25, {"diary": 3, "plaza": 2}),
        (3, 19, 6, 30, {"chat": 3, "diary": 3}),
        (0, 15, 3, 14, {"plaza": 2, "diary": 1}),
    ],
    # 冉柯 — 机械工程，早晨实验室 + 晚间调试复盘
    "ran_ke": [
        (0, 8,  6, 28, {"diary": 3, "chat": 2, "plaza": 1}),
        (1, 9,  7, 35, {"chat": 4, "diary": 3}),
        (2, 8,  6, 30, {"diary": 4, "chat": 2}),
        (3, 9,  8, 40, {"chat": 4, "diary": 3, "plaza": 1}),
        (4, 8,  5, 25, {"diary": 3, "chat": 2}),
        (5, 20, 9, 50, {"diary": 5, "chat": 4, "plaza": 2}),
        (6, 21, 8, 45, {"chat": 5, "diary": 3, "plaza": 1}),
        (0, 20, 6, 32, {"diary": 3, "chat": 3}),
        (2, 21, 7, 38, {"chat": 4, "diary": 3}),
        (4, 20, 5, 26, {"diary": 3, "plaza": 2}),
    ],
    # 周悦 — 汉语言文学，下午写作 + 深夜思维活跃
    "zhou_yue": [
        (0, 15, 6, 35, {"diary": 5, "chat": 2}),
        (1, 16, 7, 40, {"diary": 5, "plaza": 2, "chat": 1}),
        (2, 15, 6, 32, {"chat": 4, "diary": 4}),
        (3, 15, 7, 38, {"diary": 5, "plaza": 2}),
        (4, 16, 5, 28, {"diary": 4, "chat": 2}),
        (5, 21, 9, 50, {"diary": 6, "chat": 4, "plaza": 1}),
        (6, 22, 8, 45, {"chat": 5, "diary": 4}),
        (0, 22, 5, 24, {"diary": 3, "chat": 2}),
        (2, 22, 6, 30, {"diary": 4, "plaza": 1, "chat": 1}),
        (5, 15, 4, 20, {"diary": 3, "plaza": 1}),
    ],
    # 叶清 — 食品科学，清晨厨房记录 + 傍晚轻社交
    "ye_qing": [
        (0, 7,  7, 30, {"diary": 5, "plaza": 2}),
        (1, 8,  8, 38, {"diary": 5, "chat": 3}),
        (2, 7,  6, 28, {"diary": 4, "plaza": 3}),
        (3, 8,  7, 35, {"diary": 4, "chat": 3, "plaza": 1}),
        (4, 7,  6, 28, {"diary": 3, "plaza": 3}),
        (5, 19, 8, 42, {"diary": 4, "chat": 4, "avatar": 1}),
        (6, 20, 7, 38, {"chat": 4, "diary": 4, "plaza": 1}),
        (1, 19, 4, 20, {"diary": 3, "plaza": 1}),
        (3, 19, 5, 24, {"chat": 3, "diary": 2}),
        (5, 8,  4, 18, {"diary": 3, "plaza": 2}),
    ],
    # 唐朔 — 社会学，下午田野笔记 + 晚间提炼复盘
    "tang_shuo": [
        (0, 13, 6, 32, {"diary": 4, "chat": 2, "plaza": 1}),
        (1, 14, 7, 38, {"diary": 5, "plaza": 3}),
        (2, 13, 6, 30, {"chat": 4, "diary": 3}),
        (3, 14, 8, 42, {"diary": 5, "chat": 3, "plaza": 1}),
        (4, 13, 5, 26, {"diary": 3, "plaza": 2, "chat": 1}),
        (5, 20, 8, 45, {"diary": 5, "chat": 4, "plaza": 1}),
        (6, 21, 9, 50, {"chat": 5, "diary": 4, "plaza": 2}),
        (1, 20, 5, 26, {"diary": 3, "chat": 2}),
        (3, 20, 6, 30, {"chat": 3, "diary": 3}),
        (0, 15, 3, 14, {"diary": 2, "plaza": 1}),
    ],
}

# 模拟上次看到时间（按各用户典型活跃时间，取最近一天的时间戳）
LAST_SEEN_BASE = "2026-05-03"

SURF_LOG_TEMPLATES: dict[str, list[dict]] = {
    # 每个用户 3~4 条历史冲浪日志
    "xu_yining":   [("2026-05-01 21:45", 52, 3, 8, 1), ("2026-05-02 21:45", 48, 4, 10, 2), ("2026-05-03 21:50", 55, 4, 11, 1)],
    "qiao_meng":   [("2026-05-01 14:45", 45, 3, 7, 1), ("2026-05-02 20:45", 50, 4, 9, 2), ("2026-05-03 20:50", 52, 3, 8, 1)],
    "su_wen":      [("2026-05-01 22:45", 38, 2, 5, 0), ("2026-05-02 22:45", 40, 3, 7, 1), ("2026-05-03 22:50", 42, 2, 6, 1)],
    "he_zhuo":     [("2026-05-01 15:45", 44, 3, 8, 2), ("2026-05-02 21:45", 47, 4, 9, 1), ("2026-05-03 15:50", 50, 4, 10, 2)],
    "lin_yao":     [("2026-05-01 09:45", 58, 5, 12, 3), ("2026-05-02 09:45", 55, 6, 13, 2), ("2026-05-02 20:50", 52, 4, 10, 2), ("2026-05-03 09:50", 60, 5, 14, 3)],
    "jiang_nanxi": [("2026-05-01 10:45", 48, 4, 9, 1), ("2026-05-02 19:45", 44, 3, 8, 2), ("2026-05-03 10:50", 50, 4, 10, 1)],
    "ran_ke":      [("2026-05-01 08:45", 40, 3, 7, 1), ("2026-05-02 20:45", 46, 4, 9, 2), ("2026-05-03 08:50", 42, 3, 8, 1)],
    "zhou_yue":    [("2026-05-01 15:45", 44, 3, 8, 2), ("2026-05-02 22:45", 48, 4, 10, 2), ("2026-05-03 21:50", 50, 4, 11, 1)],
    "ye_qing":     [("2026-05-01 07:45", 38, 3, 7, 1), ("2026-05-02 19:45", 42, 3, 8, 2), ("2026-05-03 07:50", 40, 2, 6, 1)],
    "tang_shuo":   [("2026-05-01 13:45", 42, 4, 8, 1), ("2026-05-02 20:45", 48, 4, 10, 2), ("2026-05-03 13:50", 44, 3, 9, 1)],
}


def _default_surf_window() -> dict:
    return {"start": "09:00", "end": "23:00", "timezone": "Asia/Shanghai"}


def _default_personalized_surf_plan() -> dict:
    return {
        "mode": "cold_start",
        "confidence": 0.1,
        "preferredHours": [12, 18, 21],
        "surfSlots": [
            {"hour": 11, "minute": 45, "reason": "午间使用前预热"},
            {"hour": 17, "minute": 45, "reason": "傍晚使用前预热"},
            {"hour": 20, "minute": 45, "reason": "晚间使用前预热"},
        ],
        "quietHours": [0, 1, 2, 3, 4, 5, 6, 7],
        "dailyLimit": 3,
        "minIntervalMinutes": 180,
        "sampleSize": 0,
        "updatedAt": 0,
        "banditArms": {},
        "totalPulls": 0,
    }


def _compute_plan_from_stats(stats: list[AvatarUsageStat], now_ms: int) -> dict:
    """和 service.py 保持相同逻辑的离线版本。"""
    if not stats:
        plan = _default_personalized_surf_plan()
        plan["updatedAt"] = now_ms
        return plan

    hour_scores: dict[int, float] = {}
    total_open = 0
    total_active_ms = 0
    for stat in stats:
        recency_bonus = 8.0 if (stat.last_seen_at and now_ms - stat.last_seen_at <= 7 * 24 * 60 * 60 * 1000) else 0.0
        active_minutes = (stat.active_ms or 0) / 60000
        score = (stat.open_count or 0) * 3 + active_minutes + recency_bonus
        hour_scores[stat.hour] = hour_scores.get(stat.hour, 0) + score
        total_open += stat.open_count or 0
        total_active_ms += stat.active_ms or 0

    ranked_hours = [h for h, _ in sorted(hour_scores.items(), key=lambda x: (-x[1], x[0]))]
    preferred_hours = sorted(ranked_hours[:4]) or [12, 18, 21]
    surf_slots = []
    for hour in preferred_hours[:4]:
        slot_hour = (hour - 1) % 24
        surf_slots.append({
            "hour": slot_hour,
            "minute": 45,
            "reason": f"你通常在 {hour:02d}:00 后使用 App，提前为你预热推荐",
        })

    if total_open >= 30 or total_active_ms >= 6 * 60 * 60 * 1000:
        daily_limit, min_interval = 8, 60
    elif total_open >= 10 or total_active_ms >= 2 * 60 * 60 * 1000:
        daily_limit, min_interval = 5, 120
    else:
        daily_limit, min_interval = 3, 180

    quiet_hours = [h for h in range(0, 8) if h not in preferred_hours]
    confidence = min(0.95, round(0.2 + len(stats) / 48 + total_open / 100, 2))

    return {
        "mode": "personalized",
        "confidence": confidence,
        "preferredHours": preferred_hours,
        "surfSlots": surf_slots,
        "quietHours": quiet_hours,
        "dailyLimit": daily_limit,
        "minIntervalMinutes": min_interval,
        "sampleSize": len(stats),
        "updatedAt": now_ms,
        "banditArms": {},
        "totalPulls": 0,
    }


def _compute_next_surf_at(plan: dict, now_ms: int) -> int:
    now_local = datetime.fromtimestamp(now_ms / 1000, tz=TZ)
    slots = plan.get("surfSlots") or _default_personalized_surf_plan()["surfSlots"]
    candidates = []
    for day_offset in (0, 1, 2):
        base = now_local.date() + timedelta(days=day_offset)
        for slot in slots:
            hour = int(slot.get("hour", 12))
            minute = int(slot.get("minute", 0))
            candidate = datetime(base.year, base.month, base.day,
                                 max(0, min(hour, 23)), max(0, min(minute, 59)),
                                 tzinfo=TZ)
            if candidate > now_local:
                candidates.append(candidate)
    if not candidates:
        return now_ms + int(plan.get("minIntervalMinutes", 180)) * 60 * 1000
    best = min(candidates)
    return int(best.timestamp() * 1000)


def seed_usage_stats(db) -> dict[str, int]:
    """为 10 个用户写入使用习惯聚合数据。"""
    now = _now_ms()
    counts: dict[str, int] = {}
    for username, profile in USAGE_PROFILES.items():
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"  [WARN] 用户不存在，跳过: {username}")
            continue

        # 删除已有的 usage stats（幂等）
        db.query(AvatarUsageStat).filter(AvatarUsageStat.user_id == user.id).delete()

        created = 0
        for weekday, hour, open_count, active_minutes, page_weights in profile:
            last_seen_text = f"{LAST_SEEN_BASE} {hour:02d}:30"
            last_seen_at = _ms(last_seen_text) if hour <= 23 else _ms(f"{LAST_SEEN_BASE} 23:30")
            stat = AvatarUsageStat(
                id=str(uuid4()),
                user_id=user.id,
                weekday=weekday,
                hour=hour,
                open_count=open_count,
                active_ms=active_minutes * 60 * 1000,
                page_weights=_encode(page_weights),
                last_seen_at=last_seen_at,
                updated_at=now,
            )
            db.add(stat)
            created += 1
        counts[username] = created

    db.commit()
    return counts


def seed_avatar_status(db) -> None:
    """更新 AvatarStatus：开启自动匹配、设置个性化计划。"""
    now = _now_ms()
    for username, profile in USAGE_PROFILES.items():
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue

        stats = db.query(AvatarUsageStat).filter(AvatarUsageStat.user_id == user.id).all()
        plan = _compute_plan_from_stats(stats, now)
        next_surf_at = _compute_next_surf_at(plan, now)

        status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user.id).first()
        if not status:
            status = AvatarStatus(
                id=str(uuid4()),
                user_id=user.id,
                is_active=True,
                browsed_count=0,
                matched_count=0,
                chatting_count=0,
                last_active_at=0,
                enabled_channels=_encode(["buddy", "help", "share", "dating"]),
                enabled_actions=_encode(["browse", "match", "comment"]),
                match_range=_encode({"school": "", "distanceKm": 10,
                                     "autoReplyDailyLimit": 5, "autoReplyIntervalMinutes": 30,
                                     "autoReplyMinScore": 55}),
                surf_frequency="adaptive",
                surf_window=_encode(_default_surf_window()),
                personalized_surf_plan=_encode(plan),
                next_surf_at=next_surf_at,
                last_surf_at=0,
                daily_surf_count=0,
                daily_action_count=0,
                quiet_mode=False,
                auto_match_enabled=True,
                auto_comment_enabled=True,
                auto_publish_enabled=False,
                surf_lock_until=0,
            )
            db.add(status)
        else:
            status.surf_frequency = "adaptive"
            status.personalized_surf_plan = _encode(plan)
            status.next_surf_at = next_surf_at
            status.auto_match_enabled = True
            status.auto_comment_enabled = True
            status.quiet_mode = False

    db.commit()


def seed_surf_logs(db) -> int:
    """写入历史冲浪日志，模拟系统已经运行了几轮。"""
    total = 0
    for username, log_specs in SURF_LOG_TEMPLATES.items():
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue

        # 幂等：删除已有日志
        db.query(AvatarSurfLog).filter(AvatarSurfLog.user_id == user.id).delete()

        for started_text, scanned_posts, scanned_users, gen_matches, gen_actions in log_specs:
            started_at = _ms(started_text)
            finished_at = started_at + 3000 + gen_matches * 200
            log = AvatarSurfLog(
                id=str(uuid4()),
                user_id=user.id,
                trigger="scheduler",
                status="success",
                scanned_posts=scanned_posts,
                scanned_users=scanned_users,
                generated_matches=gen_matches,
                generated_actions=gen_actions,
                skipped_reason="",
                error_message="",
                started_at=started_at,
                finished_at=finished_at,
            )
            db.add(log)
            total += 1

    db.commit()
    return total


def print_summary(db) -> None:
    print("=" * 60)
    print("分身使用习惯数据注入完成")
    print("=" * 60)
    for username in USAGE_PROFILES:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            continue
        stat_count = db.query(AvatarUsageStat).filter(AvatarUsageStat.user_id == user.id).count()
        surf_count = db.query(AvatarSurfLog).filter(AvatarSurfLog.user_id == user.id).count()
        status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user.id).first()
        plan = _decode(status.personalized_surf_plan, {}) if status else {}
        confidence = plan.get("confidence", 0)
        preferred = plan.get("preferredHours", [])
        print(f"  {username:<14} usage_stats={stat_count}  surf_logs={surf_count}  "
              f"confidence={confidence:.2f}  preferred_hours={preferred}")
    total_stats = db.query(AvatarUsageStat).count()
    total_logs = db.query(AvatarSurfLog).count()
    print(f"\n合计: avatar_usage_stats={total_stats}  avatar_surf_logs={total_logs}")
    print("=" * 60)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        print("注入 AvatarUsageStat ...")
        stat_counts = seed_usage_stats(db)
        for k, v in stat_counts.items():
            print(f"  {k}: {v} 条")

        print("\n更新 AvatarStatus (开启自动匹配 + 写入个性化计划) ...")
        seed_avatar_status(db)

        print("\n写入历史 AvatarSurfLog ...")
        log_count = seed_surf_logs(db)
        print(f"  共写入 {log_count} 条")

        print()
        print_summary(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
