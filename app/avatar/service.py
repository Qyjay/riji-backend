"""
AI 分身模块服务层
实现记忆 CRUD、状态管理、推荐匹配、侧写生成业务逻辑

Phase 2: 反馈加权 — 将 AvatarMatch/AgentAction 的交互反馈折算为小时维度奖励分
Phase 3: UCB Bandit — 用 UCB1 算法在「利用」高奖励时段和「探索」未知时段之间权衡
Phase 5: 规则宽召回 — 三路信号（行为/关系/画像）召回用户候选 + 多维度打分
Phase 6: AI 精排 — 对规则 top-10 调用 MiniMax 生成精排分、自然理由、开场白
"""
import json
import math
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.avatar import (
    AvatarAtoaInteraction,
    AvatarAtoaSession,
    AvatarMemory,
    AvatarMatch,
    AvatarProfile,
    AvatarStatus,
    AvatarSurfLog,
    AvatarUsageStat,
)
from app.models.memory import AgentAction, AvatarCard, MemoryFact
from app.models.plaza import PlazaComment, PlazaPost, PostLike
from app.models.social import Match as SocialMatch
from app.models.user import User
from app.response import ApiException, NOT_FOUND, PARAM_INVALID


def _now_ms() -> int:
    return int(time.time() * 1000)


AVATAR_TZ = ZoneInfo("Asia/Shanghai")

# ── Phase 3: UCB Bandit 探索系数 ──────────────────────────────────────
# 值越大越倾向探索未尝试时段；1.4 是经验较好的折中值
_UCB_C = 1.4


def _encode(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _decode(s: str, default=None):
    if default is None:
        default = []
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _memory_to_dict(m: AvatarMemory) -> dict:
    """AvatarMemory ORM → 响应字典"""
    return {
        "id": m.id,
        "category": m.category or "",
        "content": m.content or "",
        "source": m.source or "manual",
        "source_ref": m.source_ref or None,
        "confidence": m.confidence if m.confidence is not None else 1.0,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
        "is_active": m.is_active if m.is_active is not None else True,
        "is_pinned": m.is_pinned or False,
        "need_type": m.need_type or None,
        "urgency": m.urgency or None,
        "expiry": m.expiry or None,
        "match_status": m.match_status or None,
        "tags": _decode(m.tags, []),
    }


def _default_match_range() -> dict:
    return {
        "school": "",
        "distanceKm": 10,
        "autoReplyDailyLimit": 5,
        "autoReplyIntervalMinutes": 30,
        "autoReplyMinScore": 55,
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
    }


def _status_to_dict(s: AvatarStatus) -> dict:
    """AvatarStatus ORM → 响应字典"""
    plan = {**_default_personalized_surf_plan(), **_decode(s.personalized_surf_plan, {})}
    window = {**_default_surf_window(), **_decode(s.surf_window, {})}
    return {
        "is_active": s.is_active if s.is_active is not None else True,
        "browsed_count": s.browsed_count or 0,
        "matched_count": s.matched_count or 0,
        "chatting_count": s.chatting_count or 0,
        "last_active_at": s.last_active_at or 0,
        "enabled_channels": _decode(s.enabled_channels, ["buddy", "help", "share", "dating"]),
        "enabled_actions": _decode(s.enabled_actions, ["browse", "match", "comment"]),
        "match_range": {**_default_match_range(), **_decode(s.match_range, {})},
        "surf_frequency": s.surf_frequency or "adaptive",
        "surf_window": window,
        "personalized_surf_plan": plan,
        "next_surf_at": s.next_surf_at or 0,
        "last_surf_at": s.last_surf_at or 0,
        "daily_surf_count": s.daily_surf_count or 0,
        "daily_action_count": s.daily_action_count or 0,
        "quiet_mode": s.quiet_mode or False,
        "auto_match_enabled": s.auto_match_enabled or False,
        "auto_comment_enabled": s.auto_comment_enabled or False,
        "auto_publish_enabled": s.auto_publish_enabled or False,
    }


# ==================== 记忆 CRUD ====================

def list_memories(db: Session, user_id: str, category: Optional[str] = None) -> List[dict]:
    """记忆列表，可按 category 筛选"""
    query = db.query(AvatarMemory).filter(AvatarMemory.user_id == user_id)
    if category:
        query = query.filter(AvatarMemory.category == category)
    memories = query.order_by(AvatarMemory.created_at.desc()).all()
    return [_memory_to_dict(m) for m in memories]


def add_memory(db: Session, user_id: str, data: dict) -> dict:
    """添加记忆"""
    now = _now_ms()
    memory = AvatarMemory(
        id=str(uuid4()),
        user_id=user_id,
        category=data["category"],
        content=data["content"],
        source="manual",
        source_ref="",
        confidence=1.0,
        is_active=True,
        is_pinned=False,
        tags=_encode([]),
        created_at=now,
        updated_at=now,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return _memory_to_dict(memory)


def update_memory(db: Session, user_id: str, memory_id: str, data: dict) -> dict:
    """更新记忆"""
    m = db.query(AvatarMemory).filter(
        AvatarMemory.id == memory_id,
        AvatarMemory.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)

    if "content" in data and data["content"] is not None:
        m.content = data["content"]
    if "is_active" in data and data["is_active"] is not None:
        m.is_active = data["is_active"]
    if "is_pinned" in data and data["is_pinned"] is not None:
        m.is_pinned = data["is_pinned"]
    if "category" in data and data["category"] is not None:
        m.category = data["category"]
    if "tags" in data and data["tags"] is not None:
        m.tags = _encode(data["tags"])

    m.updated_at = _now_ms()
    db.commit()
    db.refresh(m)
    return _memory_to_dict(m)


def delete_memory(db: Session, user_id: str, memory_id: str) -> None:
    """删除记忆"""
    m = db.query(AvatarMemory).filter(
        AvatarMemory.id == memory_id,
        AvatarMemory.user_id == user_id,
    ).first()
    if not m:
        raise ApiException(code=NOT_FOUND, message="记忆不存在", status_code=404)
    db.delete(m)
    db.commit()


# ==================== 分身状态 ====================

def _get_or_create_status(db: Session, user_id: str) -> AvatarStatus:
    """获取分身状态，首次访问自动创建默认记录"""
    status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user_id).first()
    if not status:
        status = AvatarStatus(
            id=str(uuid4()),
            user_id=user_id,
            is_active=True,
            browsed_count=0,
            matched_count=0,
            chatting_count=0,
            last_active_at=0,
            enabled_channels=_encode(["buddy", "help", "share", "dating"]),
            enabled_actions=_encode(["browse", "match", "comment"]),
            match_range=_encode(_default_match_range()),
            surf_frequency="adaptive",
            surf_window=_encode(_default_surf_window()),
            personalized_surf_plan=_encode(_default_personalized_surf_plan()),
            next_surf_at=0,
            last_surf_at=0,
            daily_surf_count=0,
            daily_action_count=0,
            quiet_mode=False,
            auto_match_enabled=False,
            auto_comment_enabled=False,
            auto_publish_enabled=False,
            surf_lock_until=0,
        )
        db.add(status)
        db.commit()
        db.refresh(status)
    return status


def _local_dt_from_ms(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=AVATAR_TZ)


def _ms_from_local(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=AVATAR_TZ)
    return int(dt.timestamp() * 1000)


# ══════════════════════════════════════════════════════════════════════
# Phase 2: 反馈加权 — 从历史交互中提取小时维度奖励信号
# ══════════════════════════════════════════════════════════════════════

def _get_feedback_hour_scores(db: Session, user_id: str, now_ms: int) -> dict:
    """
    扫描用户最近 7 天内的 AvatarMatch / AgentAction 交互，
    按「反馈发生所在小时」聚合奖励/惩罚分。

    计分规则：
      AvatarMatch.status == 'chatting'  → 该小时 +5（用户主动开聊，信号最强）
      AvatarMatch.status == 'dismissed' → 该小时 -2（用户主动拒绝，轻惩罚）
      AgentAction.status == 'published' → 该小时 +4（用户审批通过草稿）
      AgentAction.status == 'rejected'  → 该小时 -2（用户拒绝草稿）
    """
    cutoff = now_ms - 7 * 24 * 60 * 60 * 1000
    feedback: dict[int, float] = {}

    matches = (
        db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_id,
            AvatarMatch.status.in_(["chatting", "dismissed"]),
            AvatarMatch.created_at >= cutoff,
        )
        .all()
    )
    for match in matches:
        hour = _local_dt_from_ms(match.created_at).hour
        delta = 5.0 if match.status == "chatting" else -2.0
        feedback[hour] = feedback.get(hour, 0.0) + delta

    actions = (
        db.query(AgentAction)
        .filter(
            AgentAction.user_id == user_id,
            AgentAction.status.in_(["published", "rejected"]),
            AgentAction.created_at >= cutoff,
        )
        .all()
    )
    for action in actions:
        hour = _local_dt_from_ms(action.created_at).hour
        delta = 4.0 if action.status == "published" else -2.0
        feedback[hour] = feedback.get(hour, 0.0) + delta

    return feedback


# ══════════════════════════════════════════════════════════════════════
# Phase 3: UCB Bandit — 探索 vs. 利用权衡
# ══════════════════════════════════════════════════════════════════════

def _ucb_score(mean_reward: float, arm_pulls: int, total_pulls: int) -> float:
    """
    UCB1 公式：均值奖励 + 探索加成。
    未被探索的臂（arm_pulls=0）返回 +inf，确保每个时间槽至少被探索一次。
    """
    if arm_pulls == 0 or total_pulls == 0:
        return float("inf")
    return mean_reward + _UCB_C * math.sqrt(math.log(total_pulls) / arm_pulls)


def _ucb_reorder_slots(surf_slots: list, bandit_arms: dict, total_pulls: int) -> list:
    """
    按 UCB 分数对冲浪时间槽降序排列，让高奖励时段优先，
    同时给从未探索过的时段保留机会。
    """
    def slot_ucb(slot: dict) -> float:
        hour = slot.get("hour", 0)
        arm = bandit_arms.get(f"hour_{hour}", {})
        return _ucb_score(
            mean_reward=float(arm.get("mean_reward", 0.0)),
            arm_pulls=int(arm.get("pulls", 0)),
            total_pulls=total_pulls,
        )

    return sorted(surf_slots, key=slot_ucb, reverse=True)


def _compute_personalized_surf_plan(db: Session, user_id: str, now_ms: Optional[int] = None) -> dict:
    """基于 App 使用聚合习惯生成私人化冲浪计划。"""
    now_ms = now_ms or _now_ms()
    stats = db.query(AvatarUsageStat).filter(AvatarUsageStat.user_id == user_id).all()
    if not stats:
        plan = _default_personalized_surf_plan()
        plan["updatedAt"] = now_ms
        return plan

    # ── Phase 1: 使用习惯基础分 ─────────────────────────────────────────
    hour_scores: dict[int, float] = {}
    total_open = 0
    total_active_ms = 0
    for stat in stats:
        recency_bonus = 0
        if stat.last_seen_at and now_ms - stat.last_seen_at <= 7 * 24 * 60 * 60 * 1000:
            recency_bonus = 8
        active_minutes = (stat.active_ms or 0) / 60000
        score = (stat.open_count or 0) * 3 + active_minutes + recency_bonus
        hour_scores[stat.hour] = hour_scores.get(stat.hour, 0) + score
        total_open += stat.open_count or 0
        total_active_ms += stat.active_ms or 0

    # ── Phase 2: 叠加反馈信号 ────────────────────────────────────────────
    # 将用户历史交互（接受/拒绝匹配、审批/拒绝草稿）折算为奖励/惩罚分
    feedback_scores = _get_feedback_hour_scores(db, user_id, now_ms)
    for hour, feedback in feedback_scores.items():
        # 反馈权重乘以 3，与使用习惯分处于同一数量级但稍低
        hour_scores[hour] = hour_scores.get(hour, 0.0) + feedback * 3.0

    ranked_hours = [
        hour for hour, _ in sorted(hour_scores.items(), key=lambda item: (-item[1], item[0]))
    ]
    preferred_hours = sorted(ranked_hours[:4]) or [12, 18, 21]
    surf_slots = []
    for hour in preferred_hours[:4]:
        slot_hour = (hour - 1) % 24
        feedback_note = ""
        if hour in feedback_scores and feedback_scores[hour] > 0:
            feedback_note = "，且历史上这个时段你更愿意接受推荐"
        elif hour in feedback_scores and feedback_scores[hour] < 0:
            feedback_note = "，但这个时段你过去常常跳过推荐，已降权"
        surf_slots.append({
            "hour": slot_hour,
            "minute": 45,
            "reason": f"你通常在 {hour:02d}:00 后使用 App，提前为你预热推荐{feedback_note}",
        })

    if total_open >= 30 or total_active_ms >= 6 * 60 * 60 * 1000:
        daily_limit = 8
        min_interval = 60
    elif total_open >= 10 or total_active_ms >= 2 * 60 * 60 * 1000:
        daily_limit = 5
        min_interval = 120
    else:
        daily_limit = 3
        min_interval = 180

    quiet_hours = [hour for hour in range(0, 8) if hour not in preferred_hours]
    confidence = min(0.95, round(0.2 + len(stats) / 48 + total_open / 100, 2))

    # ── Phase 3: UCB Bandit 排序 ─────────────────────────────────────────
    # 读取历史 Bandit 臂状态，按 UCB 分数重排冲浪时间槽
    existing_status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user_id).first()
    existing_plan = _decode(existing_status.personalized_surf_plan, {}) if existing_status else {}
    bandit_arms = existing_plan.get("banditArms", {})
    total_pulls = int(existing_plan.get("totalPulls", 0))
    if total_pulls > 0:
        surf_slots = _ucb_reorder_slots(surf_slots, bandit_arms, total_pulls)

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
        "banditArms": bandit_arms,
        "totalPulls": total_pulls,
        "feedbackHours": {str(k): round(v, 1) for k, v in feedback_scores.items()},
    }


def compute_next_surf_at_from_plan(plan: dict, now_ms: Optional[int] = None) -> int:
    """从私人化计划里选择下一个冲浪时间点。"""
    now_ms = now_ms or _now_ms()
    now_local = _local_dt_from_ms(now_ms)
    slots = plan.get("surfSlots") or _default_personalized_surf_plan()["surfSlots"]
    candidates = []
    for day_offset in (0, 1, 2):
        base_date = now_local.date() + timedelta(days=day_offset)
        for slot in slots:
            hour = int(slot.get("hour", 12))
            minute = int(slot.get("minute", 0))
            candidate = datetime(
                base_date.year,
                base_date.month,
                base_date.day,
                max(0, min(hour, 23)),
                max(0, min(minute, 59)),
                tzinfo=AVATAR_TZ,
            )
            if candidate > now_local:
                candidates.append(candidate)
    if not candidates:
        return now_ms + int(plan.get("minIntervalMinutes") or 180) * 60 * 1000
    return _ms_from_local(min(candidates))


def _refresh_status_plan(db: Session, status: AvatarStatus, now_ms: Optional[int] = None) -> None:
    now_ms = now_ms or _now_ms()
    plan = _compute_personalized_surf_plan(db, status.user_id, now_ms)
    status.personalized_surf_plan = _encode(plan)
    if status.auto_match_enabled or status.auto_comment_enabled:
        status.next_surf_at = compute_next_surf_at_from_plan(plan, now_ms)


def update_bandit_feedback(db: Session, user_id: str, reward: float) -> None:
    """
    记录用户对上次冲浪结果的反馈，更新 UCB Bandit 臂的累计奖励。（Phase 3）

    反馈归因规则：以 AvatarStatus.last_surf_at 的小时作为被更新的臂，
    即「上次冲浪发生在几点，就把这次反馈记到那个小时的臂上」。

    奖励参考：
      用户批准 AgentAction → reward = +4.0
      用户拒绝 AgentAction → reward = -2.0
      （从推荐发起搭子见 `start_chat_from_match`，reward = +10.0）
    """
    status = db.query(AvatarStatus).filter(AvatarStatus.user_id == user_id).first()
    if not status or not status.last_surf_at:
        return

    arm_hour = _local_dt_from_ms(status.last_surf_at).hour
    key = f"hour_{arm_hour}"

    plan = _decode(status.personalized_surf_plan, _default_personalized_surf_plan())
    bandit_arms = plan.get("banditArms") or {}
    arm = bandit_arms.get(key, {"pulls": 0, "total_reward": 0.0, "mean_reward": 0.0})

    arm["total_reward"] = float(arm.get("total_reward", 0.0)) + reward
    pulls = max(1, int(arm.get("pulls", 1)))
    arm["mean_reward"] = round(arm["total_reward"] / pulls, 3)

    bandit_arms[key] = arm
    plan["banditArms"] = bandit_arms
    plan["lastRewardAt"] = _now_ms()

    status.personalized_surf_plan = _encode(plan)
    db.commit()


async def run_avatar_surf_for_user(db: Session, user_id: str, trigger: str = "scheduler") -> dict:
    """
    为单个用户执行一次完整冲浪循环（方案B 调度器调用入口）：

    1. 检查分身是否开启、是否在静默模式
    2. 检查幂等锁，防止重复调度
    3. 调用 _refresh_matches_async（含 AtoA 探针通道）
    4. 记录 AvatarSurfLog（含 AtoA 统计 + surf_report）
    5. 更新 last_surf_at、daily_surf_count、next_surf_at
    6. 在 Bandit 臂里记录一次 pull（探索次数 +1）
    """
    now = _now_ms()
    status = _get_or_create_status(db, user_id)

    if not status.is_active:
        return {"status": "skipped", "reason": "分身未开启"}
    if status.quiet_mode:
        return {"status": "skipped", "reason": "安静模式"}
    if not (status.auto_match_enabled or status.auto_comment_enabled):
        return {"status": "skipped", "reason": "未开启自动冲浪"}
    if (status.surf_lock_until or 0) > now:
        return {"status": "skipped", "reason": "正在执行中，已跳过重复调度"}

    # 获取幂等锁（5 分钟有效期）
    status.surf_lock_until = now + 5 * 60 * 1000
    db.commit()

    log = AvatarSurfLog(
        id=str(uuid4()),
        user_id=user_id,
        trigger=trigger,
        status="running",
        scanned_posts=0,
        scanned_users=0,
        generated_matches=0,
        generated_actions=0,
        skipped_reason="",
        error_message="",
        started_at=now,
        finished_at=None,
    )
    db.add(log)
    db.commit()

    try:
        surf_stats = await _refresh_matches_async(db, user_id)

        new_matches_count = (
            db.query(AvatarMatch)
            .filter(
                AvatarMatch.user_id == user_id,
                AvatarMatch.status == "new",
                AvatarMatch.created_at >= now - 24 * 60 * 60 * 1000,
            )
            .count()
        )

        # 记录 Bandit 臂 pull（Phase 3）
        arm_hour = _local_dt_from_ms(now).hour
        key = f"hour_{arm_hour}"
        plan = _decode(status.personalized_surf_plan, _default_personalized_surf_plan())
        bandit_arms = plan.get("banditArms") or {}
        arm = bandit_arms.get(key, {"pulls": 0, "total_reward": 0.0, "mean_reward": 0.0})
        arm["pulls"] = int(arm.get("pulls", 0)) + 1
        bandit_arms[key] = arm
        plan["banditArms"] = bandit_arms
        plan["totalPulls"] = int(plan.get("totalPulls", 0)) + 1
        status.personalized_surf_plan = _encode(plan)

        status.last_surf_at = now
        status.daily_surf_count = (status.daily_surf_count or 0) + 1
        status.next_surf_at = compute_next_surf_at_from_plan(plan, _now_ms())
        status.surf_lock_until = 0

        # Phase 8A: 写入 AtoA 统计、surf_report 和 top10_session_id
        atoa_scanned = surf_stats.get("atoa_scanned", 0)
        atoa_mutual = surf_stats.get("atoa_mutual", 0)
        atoa_one_sided = surf_stats.get("atoa_one_sided", 0)
        top10_session_id = surf_stats.get("session_id")
        log.scanned_atoa_pairs = atoa_scanned
        log.upgraded_to_mutual = atoa_mutual
        log.top10_session_id = top10_session_id
        log.surf_report = generate_surf_report(
            atoa_scanned, atoa_mutual, atoa_one_sided,
            surf_stats.get("matched", 0),
        )

        # 同步 session.surf_log_id
        if top10_session_id:
            _session = db.query(AvatarAtoaSession).filter(
                AvatarAtoaSession.id == top10_session_id
            ).first()
            if _session:
                _session.surf_log_id = log.id

        log.status = "success"
        log.generated_matches = new_matches_count
        log.finished_at = _now_ms()
        db.commit()

        return {
            "status": "success",
            "generated_matches": new_matches_count,
            "atoa_scanned": atoa_scanned,
            "atoa_mutual": atoa_mutual,
            "surf_report": log.surf_report,
            "top10_session_id": top10_session_id,
            "user_id": user_id,
        }

    except Exception as exc:
        log.status = "failed"
        log.error_message = str(exc)[:500]
        log.finished_at = _now_ms()
        status.surf_lock_until = 0
        status.next_surf_at = now + 30 * 60 * 1000
        db.commit()
        raise


def get_status(db: Session, user_id: str) -> dict:
    """获取分身状态"""
    status = _get_or_create_status(db, user_id)
    return _status_to_dict(status)


def update_status(db: Session, user_id: str, data: dict) -> dict:
    """更新分身状态"""
    status = _get_or_create_status(db, user_id)
    allowed_frequency = {"adaptive", "low", "medium", "high", "custom"}

    if "is_active" in data and data["is_active"] is not None:
        status.is_active = data["is_active"]
    if "enabled_channels" in data and data["enabled_channels"] is not None:
        status.enabled_channels = _encode(data["enabled_channels"])
    if "enabled_actions" in data and data["enabled_actions"] is not None:
        status.enabled_actions = _encode(data["enabled_actions"])
    if "match_range" in data and data["match_range"] is not None:
        status.match_range = _encode(data["match_range"])
    if "surf_frequency" in data and data["surf_frequency"] is not None:
        if data["surf_frequency"] not in allowed_frequency:
            raise ApiException(code=PARAM_INVALID, message="surf_frequency 不合法")
        status.surf_frequency = data["surf_frequency"]
    if "surf_window" in data and data["surf_window"] is not None:
        status.surf_window = _encode({**_default_surf_window(), **data["surf_window"]})
    if "quiet_mode" in data and data["quiet_mode"] is not None:
        status.quiet_mode = data["quiet_mode"]
    if "auto_match_enabled" in data and data["auto_match_enabled"] is not None:
        status.auto_match_enabled = data["auto_match_enabled"]
    if "auto_comment_enabled" in data and data["auto_comment_enabled"] is not None:
        status.auto_comment_enabled = data["auto_comment_enabled"]
    if "auto_publish_enabled" in data and data["auto_publish_enabled"] is not None:
        status.auto_publish_enabled = data["auto_publish_enabled"]

    if status.auto_publish_enabled and not status.auto_comment_enabled:
        raise ApiException(code=PARAM_INVALID, message="开启自动发布前必须先开启自动评论草稿")

    if status.surf_frequency == "adaptive":
        _refresh_status_plan(db, status)

    db.commit()
    db.refresh(status)
    return _status_to_dict(status)


def record_usage_event(db: Session, user_id: str, data: dict) -> dict:
    """记录 App 使用习惯聚合，用于个性化分身冲浪计划。"""
    event_type = data.get("event_type")
    allowed_events = {"app_open", "app_resume", "app_close", "active_ping", "page_view"}
    if event_type not in allowed_events:
        raise ApiException(code=PARAM_INVALID, message="event_type 不合法")

    now = _now_ms()
    timestamp = int(data.get("timestamp") or now)
    active_ms = max(0, min(int(data.get("active_ms") or 0), 6 * 60 * 60 * 1000))
    page = str(data.get("page") or "").strip()[:40]
    local_dt = _local_dt_from_ms(timestamp)
    weekday = local_dt.weekday()
    hour = local_dt.hour

    stat = (
        db.query(AvatarUsageStat)
        .filter(
            AvatarUsageStat.user_id == user_id,
            AvatarUsageStat.weekday == weekday,
            AvatarUsageStat.hour == hour,
        )
        .first()
    )
    if not stat:
        stat = AvatarUsageStat(
            id=str(uuid4()),
            user_id=user_id,
            weekday=weekday,
            hour=hour,
            open_count=0,
            active_ms=0,
            page_weights=_encode({}),
            last_seen_at=timestamp,
            updated_at=now,
        )
        db.add(stat)

    if event_type in {"app_open", "app_resume"}:
        stat.open_count = (stat.open_count or 0) + 1
    if event_type in {"active_ping", "app_close"}:
        stat.active_ms = (stat.active_ms or 0) + active_ms
    if page:
        weights = _decode(stat.page_weights, {})
        weights[page] = int(weights.get(page, 0)) + 1
        stat.page_weights = _encode(weights)

    stat.last_seen_at = max(stat.last_seen_at or 0, timestamp)
    stat.updated_at = now
    status = _get_or_create_status(db, user_id)
    status.last_active_at = max(status.last_active_at or 0, timestamp)
    _refresh_status_plan(db, status, now)
    db.commit()
    db.refresh(status)
    return {
        "recorded": True,
        "personalized_surf_plan": _decode(status.personalized_surf_plan, _default_personalized_surf_plan()),
        "next_surf_at": status.next_surf_at or 0,
        "recorded_at": now,
    }


def _surf_log_to_dict(log: AvatarSurfLog) -> dict:
    return {
        "id": log.id,
        "trigger": log.trigger or "",
        "status": log.status or "success",
        "scanned_posts": log.scanned_posts or 0,
        "scanned_users": log.scanned_users or 0,
        "generated_matches": log.generated_matches or 0,
        "generated_actions": log.generated_actions or 0,
        "skipped_reason": log.skipped_reason or "",
        "error_message": log.error_message or "",
        "started_at": log.started_at,
        "finished_at": log.finished_at,
        "scanned_atoa_pairs": getattr(log, "scanned_atoa_pairs", None) or 0,
        "upgraded_to_mutual": getattr(log, "upgraded_to_mutual", None) or 0,
        "surf_report": getattr(log, "surf_report", None) or "",
        "top10_session_id": getattr(log, "top10_session_id", None),
    }


def list_surf_logs(db: Session, user_id: str, limit: int = 20) -> dict:
    safe_limit = max(1, min(int(limit or 20), 100))
    query = db.query(AvatarSurfLog).filter(AvatarSurfLog.user_id == user_id)
    total = query.count()
    logs = query.order_by(AvatarSurfLog.started_at.desc()).limit(safe_limit).all()
    return {"items": [_surf_log_to_dict(log) for log in logs], "total": total}


# ==================== 分身推荐 ====================

def _post_to_dict(post: PlazaPost, user: User) -> dict:
    """复用广场帖子序列化（避免循环导入，独立实现）"""
    return {
        "id": post.id,
        "author_id": post.user_id,
        "author_name": user.name or user.username,
        "author_avatar": user.avatar or "",
        "author_school": user.school or "",
        "author_major": user.major or "",
        "author_grade": user.grade or "",
        "type": post.type,
        "content": post.content or "",
        "images": _decode(post.images, []),
        "location": post.location or "",
        "tags": _decode(post.tags, []),
        "likes": post.likes or 0,
        "comments": post.comments or 0,
        "agent_responses": post.agent_responses or 0,
        "created_at": post.created_at,
        "is_from_agent": post.is_from_agent or False,
        "allow_agent_reply": post.allow_agent_reply if post.allow_agent_reply is not None else True,
        "school_only": post.school_only or False,
    }


def _tokenize_text(value: str) -> list[str]:
    import re

    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", str(value or "").lower())
    return list(dict.fromkeys(tokens))


def _collect_match_keywords(db: Session, user_id: str) -> dict:
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.is_pinned.desc(), MemoryFact.updated_at.desc())
        .limit(40)
        .all()
    )
    memories = (
        db.query(AvatarMemory)
        .filter(AvatarMemory.user_id == user_id, AvatarMemory.is_active == True)  # noqa: E712
        .order_by(AvatarMemory.is_pinned.desc(), AvatarMemory.updated_at.desc())
        .limit(20)
        .all()
    )
    interests = _decode(card.interest_tags, []) if card else []
    intents = _decode(card.social_intent, []) if card else []
    boundaries = _decode(card.boundaries, []) if card else []
    profile_summary = card.public_summary if card else ""

    for fact in facts:
        text = (fact.content or "").strip()
        if not text:
            continue
        if fact.category in {"interest", "preference", "habit"} and len(interests) < 16:
            interests.append(text[:30])
        elif fact.category == "need" and len(intents) < 8:
            intents.append(text[:40])
        elif fact.category == "boundary" and len(boundaries) < 8:
            boundaries.append(text[:60])

    if len(interests) < 16:
        for memory in memories:
            if memory.category in {"interest", "habit", "need"}:
                interests.append((memory.content or "")[:30])

    interest_tokens = set()
    for item in interests:
        interest_tokens.update(_tokenize_text(item))
    intent_tokens = set()
    for item in intents:
        intent_tokens.update(_tokenize_text(item))
    profile_tokens = set(_tokenize_text(profile_summary))

    return {
        "card": card,
        "interests": list(dict.fromkeys([item for item in interests if item])),
        "intents": list(dict.fromkeys([item for item in intents if item])),
        "boundaries": list(dict.fromkeys([item for item in boundaries if item])),
        "interest_tokens": interest_tokens,
        "intent_tokens": intent_tokens,
        "profile_tokens": profile_tokens,
    }


def _match_channel_reason(post_type: str, intents: list[str]) -> Optional[str]:
    text = " ".join(intents)
    mapping = {
        "buddy": ["搭子", "一起", "陪伴", "结伴", "自习"],
        "help": ["帮助", "求助", "建议", "支持"],
        "share": ["分享", "交流", "记录", "看看"],
        "dating": ["恋爱", "心动", "约会", "认识"],
    }
    if any(keyword in text for keyword in mapping.get(post_type, [])):
        return f"你的社交意图里包含和「{post_type}」频道相近的需求"
    return None


def _build_match_for_post(db: Session, current_user: User, post: PlazaPost, author: User, inputs: dict) -> Optional[dict]:
    from app.memory.retriever import retrieve_shared_memories

    reasons = []
    score = 0
    seen = set()
    post_tags = _decode(post.tags, [])
    post_text = f"{post.content or ''} {' '.join(post_tags)} {post.location or ''}".lower()
    post_tokens = set(_tokenize_text(post_text))

    def _push_reason(reason: str, delta: int) -> None:
        nonlocal score
        if reason and reason not in seen:
            reasons.append(reason)
            seen.add(reason)
            score += delta

    if (author.school or "") and (author.school or "") == (current_user.school or ""):
        _push_reason("你们在同一所学校，线下交流成本更低", 18)

    channel_reason = _match_channel_reason(post.type or "", inputs["intents"])
    if channel_reason:
        _push_reason(channel_reason, 14)

    shared_interest_tokens = sorted(inputs["interest_tokens"].intersection(post_tokens))
    if shared_interest_tokens:
        _push_reason(f"帖子内容命中了你的兴趣关键词：{' / '.join(shared_interest_tokens[:3])}", 20)

    author_card = db.query(AvatarCard).filter(AvatarCard.user_id == post.user_id).first()
    if author_card:
        author_interests = set(_tokenize_text(" ".join(_decode(author_card.interest_tags, []))))
        overlap = sorted(inputs["interest_tokens"].intersection(author_interests))
        if overlap:
            _push_reason(f"你和对方分身名片里都提到了：{' / '.join(overlap[:3])}", 16)

    shared_memories = retrieve_shared_memories(
        db,
        owner_user_id=post.user_id,
        query=" ".join(list(inputs["interest_tokens"])[:6] + list(inputs["intent_tokens"])[:4]),
        scenario="plaza_match",
        top_k=2,
        source_types=["plaza_post_index"],
        viewer_school=current_user.school or "",
        owner_school=author.school or "",
    )
    for memory in shared_memories[:2]:
        title = memory.get("title") or "对方公开记忆"
        snippet = (memory.get("summary") or memory.get("content") or "").strip()
        if snippet:
            _push_reason(f"{title} 里也出现了与你相关的话题：{snippet[:24]}", 12)

    if post.allow_agent_reply:
        _push_reason("这条帖子允许分身先打个招呼，适合低压力开启互动", 6)

    if score < 20 or not reasons:
        return None

    conversation = []
    if author_card and inputs["card"]:
        conversation = [
            {
                "from": "my_agent",
                "content": f"我主人可能会对这条内容感兴趣，尤其是 {', '.join(inputs['interests'][:2]) or '你们的共同话题'}。",
                "timestamp": _now_ms(),
            },
            {
                "from": "their_agent",
                "content": f"我的主人最近也愿意聊聊 {', '.join(_decode(author_card.interest_tags, [])[:2]) or '这些话题'}。",
                "timestamp": _now_ms(),
            },
        ]

    return {
        "score": min(score, 99),
        "reasons": reasons[:4],
        "agent_conversation": conversation[:2],
    }


# ==================== Phase 5: 用户候选宽召回 ====================

def _recall_user_candidates(
    db: Session,
    user_id: str,
    current_user: User,
    inputs: dict,
) -> List[Tuple[User, dict]]:
    """
    三路信号召回用户候选，返回 (User, signals) 列表。

    信号维度：
      has_social_match    — 已有社交搭子关系（最强信号）
      comment_to_them     — 我主动评论过 TA 的帖子
      comment_to_me       — TA 主动评论过我的帖子（对方表现出兴趣）
      like_to_them        — 我点赞过 TA 的帖子
      same_post_overlap   — 双方都参与互动了同一篇帖子
      interest_overlap    — 分身名片兴趣词重合数（画像维度）
    """
    candidate_signals: dict[str, dict] = {}

    def _sig(uid: str) -> dict:
        if uid not in candidate_signals:
            candidate_signals[uid] = {
                "has_social_match": False,
                "comment_to_them": 0,
                "comment_to_me": 0,
                "like_to_them": 0,
                "same_post_overlap": 0,
                "interest_overlap": 0,
            }
        return candidate_signals[uid]

    # --- 信号 1: 关系召回（已接受的社交搭子）---
    social_rows = (
        db.query(SocialMatch)
        .filter(
            or_(SocialMatch.user_id == user_id, SocialMatch.target_id == user_id),
            SocialMatch.status == "accepted",
        )
        .all()
    )
    for sm in social_rows:
        other = sm.target_id if sm.user_id == user_id else sm.user_id
        if other and other != user_id:
            _sig(other)["has_social_match"] = True

    # --- 信号 2: 行为召回（近 14 天的评论/点赞交互）---
    fourteen_days_ago = _now_ms() - 14 * 24 * 60 * 60 * 1000

    # 我评论了哪些帖子 → 取帖子作者
    my_comment_post_ids = [
        r[0]
        for r in db.query(PlazaComment.post_id)
        .filter(
            PlazaComment.user_id == user_id,
            PlazaComment.is_agent == False,  # noqa: E712
            PlazaComment.created_at >= fourteen_days_ago,
        )
        .distinct()
        .all()
    ]
    if my_comment_post_ids:
        for (author_id,) in (
            db.query(PlazaPost.user_id)
            .filter(
                PlazaPost.id.in_(my_comment_post_ids),
                PlazaPost.user_id != user_id,
            )
            .all()
        ):
            _sig(author_id)["comment_to_them"] += 1

    # 谁评论了我的帖子
    my_post_ids = [r[0] for r in db.query(PlazaPost.id).filter(PlazaPost.user_id == user_id).all()]
    if my_post_ids:
        for (commenter_id,) in (
            db.query(PlazaComment.user_id)
            .filter(
                PlazaComment.post_id.in_(my_post_ids),
                PlazaComment.user_id != user_id,
                PlazaComment.is_agent == False,  # noqa: E712
                PlazaComment.created_at >= fourteen_days_ago,
            )
            .distinct()
            .all()
        ):
            _sig(commenter_id)["comment_to_me"] += 1

    # 我点赞了哪些帖子 → 取帖子作者
    my_liked_post_ids = [
        r[0]
        for r in db.query(PostLike.post_id)
        .filter(PostLike.user_id == user_id)
        .all()
    ]
    if my_liked_post_ids:
        for (author_id,) in (
            db.query(PlazaPost.user_id)
            .filter(
                PlazaPost.id.in_(my_liked_post_ids),
                PlazaPost.user_id != user_id,
            )
            .all()
        ):
            _sig(author_id)["like_to_them"] += 1

    # 共同互动信号：双方都评论/点赞了同一帖子
    all_engaged = set(my_comment_post_ids) | set(my_liked_post_ids)
    if all_engaged:
        for (other_id,) in (
            db.query(PlazaComment.user_id)
            .filter(
                PlazaComment.post_id.in_(list(all_engaged)[:30]),
                PlazaComment.user_id != user_id,
                PlazaComment.is_agent == False,  # noqa: E712
            )
            .distinct()
            .all()
        ):
            _sig(other_id)["same_post_overlap"] += 1

    # --- 信号 3: 画像相似召回（分身名片兴趣词重合）---
    all_cards = db.query(AvatarCard).filter(AvatarCard.user_id != user_id).all()
    for card in all_cards:
        card_tokens = set(_tokenize_text(" ".join(_decode(card.interest_tags, []))))
        overlap = len(inputs["interest_tokens"].intersection(card_tokens))
        if overlap >= 2:
            _sig(card.user_id)["interest_overlap"] = overlap

    # 只保留有实际信号的候选人
    meaningful = {
        uid: sig
        for uid, sig in candidate_signals.items()
        if (
            sig["has_social_match"]
            or sig["comment_to_them"] > 0
            or sig["comment_to_me"] > 0
            or sig["like_to_them"] > 0
            or sig["same_post_overlap"] > 0
            or sig["interest_overlap"] >= 3
        )
    }
    if not meaningful:
        return []

    candidate_users = db.query(User).filter(User.id.in_(list(meaningful.keys()))).all()
    return [(u, meaningful[u.id]) for u in candidate_users]


def _rule_score_user_match(
    db: Session,
    current_user: User,
    candidate: User,
    inputs: dict,
    signals: dict,
) -> Optional[dict]:
    """
    Phase 5: 规则多信号打分（用户 vs 用户）。
    返回 {score, reasons, intent_type} 或 None（低于阈值则不推荐）。
    """
    reasons: list[str] = []
    score = 0
    seen: set = set()

    def _push(reason: str, delta: int) -> None:
        nonlocal score
        if reason and reason not in seen:
            reasons.append(reason)
            seen.add(reason)
            score += delta

    # 学校信号（最基础社交信任）
    if (candidate.school or "") and (candidate.school or "") == (current_user.school or ""):
        _push("你们在同一所学校，随时可以见面", 18)

    # 社交关系信号（已有搭子关系）
    if signals.get("has_social_match"):
        _push("你们已经是搭子关系，分身觉得可以进一步了解", 25)

    # 行为互动信号
    if signals.get("comment_to_them", 0) > 0:
        _push("你最近评论过 TA 的帖子，说明你对 TA 有兴趣", 12)
    if signals.get("comment_to_me", 0) > 0:
        _push("TA 最近在你的帖子下留言，可能也想认识你", 14)
    if signals.get("like_to_them", 0) > 0:
        _push("你对 TA 的内容点过赞，有共鸣", 8)

    same_post = min(signals.get("same_post_overlap", 0), 3)
    if same_post > 0:
        _push(
            f"你们都参与了 {same_post} 篇相同帖子的互动，话题品味相近",
            min(same_post * 8, 24),
        )

    # 兴趣画像信号
    interest_overlap = signals.get("interest_overlap", 0)
    if interest_overlap >= 3:
        _push(f"你们的分身名片兴趣词重合了 {interest_overlap} 个，圈子很像", min(interest_overlap * 5, 25))
    elif interest_overlap >= 2:
        _push("你们的分身名片里有共同的兴趣词", 10)

    # 社交意图信号
    candidate_card = db.query(AvatarCard).filter(AvatarCard.user_id == candidate.id).first()
    if candidate_card:
        cand_intents = set(str(t) for t in _decode(candidate_card.social_intent, []))
        my_intents = set(str(t) for t in inputs.get("intents", []))
        if cand_intents.intersection(my_intents):
            _push("你们的社交意图方向接近，开聊不会尴尬", 14)

    if score < 20 or not reasons:
        return None

    # 推断主要意图类型
    cand_intents_list = _decode(candidate_card.social_intent, []) if candidate_card else []
    intent_type = "buddy"
    if cand_intents_list:
        first = str(cand_intents_list[0]).lower()
        if any(w in first for w in ["恋爱", "心动", "约会", "dating"]):
            intent_type = "dating"
        elif any(w in first for w in ["帮助", "求助", "support", "help"]):
            intent_type = "help"
        elif any(w in first for w in ["分享", "交流", "share"]):
            intent_type = "share"

    return {
        "score": min(score, 99),
        "reasons": reasons[:4],
        "intent_type": intent_type,
    }


# ==================== Phase 8A: AtoA 双向分身探针 ====================

# 双方均达阈值才算 mutual；仅 A 达阈值算 one_sided
_ATOA_MUTUAL_THRESHOLD = 25
# 规则预筛最低分（低于此分直接跳过，不调用 AI）
_ATOA_PREFILTER_THRESHOLD = 10
# 全系统 auto_match_enabled=True 用户数低于此值时，AtoA 通道冷启动跳过
_ATOA_COLD_START_MIN_USERS = 3
# 每次冲浪展示给用户的最多候选数
_ATOA_TOP_N = 10
# 用户打断时双向降分幅度
_ATOA_BLOCK_PENALTY = 10


def _recall_atoa_candidates(db: Session, user_id: str) -> list[User]:
    """
    AtoA 专用召回：返回满足 AtoA 条件的候选用户列表。
    条件（全部满足）：
      1. AvatarStatus.is_active = True
      2. AvatarStatus.auto_match_enabled = True  ← 关键门槛
      3. AvatarCard.visibility != "private"
      4. 我未曾 dismiss 对方
      5. 对方未曾 dismiss 我
    """
    # 我曾 dismiss 的用户 ID 集合
    i_dismissed: set[str] = {
        row.target_user_id
        for row in db.query(AvatarMatch.target_user_id)
        .filter(
            AvatarMatch.user_id == user_id,
            AvatarMatch.status == "dismissed",
            AvatarMatch.target_user_id != None,  # noqa: E711
        )
        .all()
    }

    # 对方曾 dismiss 我的用户 ID 集合
    dismissed_me: set[str] = {
        row.user_id
        for row in db.query(AvatarMatch.user_id)
        .filter(
            AvatarMatch.target_user_id == user_id,
            AvatarMatch.status == "dismissed",
            AvatarMatch.match_type == "atoa",
        )
        .all()
    }

    blocked = i_dismissed | dismissed_me

    # 查 auto_match_enabled=True 且有可见名片的用户
    eligible_user_ids: list[str] = []
    statuses = (
        db.query(AvatarStatus)
        .filter(
            AvatarStatus.user_id != user_id,
            AvatarStatus.is_active == True,  # noqa: E712
            AvatarStatus.auto_match_enabled == True,  # noqa: E712
        )
        .all()
    )
    for st in statuses:
        if st.user_id in blocked:
            continue
        card = db.query(AvatarCard).filter(AvatarCard.user_id == st.user_id).first()
        if card and card.visibility != "private":
            eligible_user_ids.append(st.user_id)

    if not eligible_user_ids:
        return []
    return db.query(User).filter(User.id.in_(eligible_user_ids)).all()


def _collect_interaction_signals_for_pair(
    db: Session, user_a_id: str, user_b_id: str
) -> dict:
    """
    收集 A 与 B 之间的有方向性双向互动信号。
    返回 {comment_a_to_b, comment_b_to_a, like_a_to_b, same_post_overlap, has_social_match}。
    """
    # A 评论了 B 的帖子
    b_post_ids = [
        row.id for row in db.query(PlazaPost.id).filter(PlazaPost.user_id == user_b_id).all()
    ]
    comment_a_to_b = (
        db.query(PlazaComment)
        .filter(PlazaComment.user_id == user_a_id, PlazaComment.post_id.in_(b_post_ids))
        .count()
        if b_post_ids else 0
    )

    # B 评论了 A 的帖子
    a_post_ids = [
        row.id for row in db.query(PlazaPost.id).filter(PlazaPost.user_id == user_a_id).all()
    ]
    comment_b_to_a = (
        db.query(PlazaComment)
        .filter(PlazaComment.user_id == user_b_id, PlazaComment.post_id.in_(a_post_ids))
        .count()
        if a_post_ids else 0
    )

    # A 点赞了 B 的帖子
    like_a_to_b = (
        db.query(PostLike)
        .filter(PostLike.user_id == user_a_id, PostLike.post_id.in_(b_post_ids))
        .count()
        if b_post_ids else 0
    )

    # 双方都参与过的帖子数
    a_engaged = set(a_post_ids)
    b_engaged = set(b_post_ids)
    if a_engaged and b_engaged:
        a_commented = {
            row.post_id
            for row in db.query(PlazaComment.post_id)
            .filter(PlazaComment.user_id == user_a_id)
            .all()
        }
        b_commented = {
            row.post_id
            for row in db.query(PlazaComment.post_id)
            .filter(PlazaComment.user_id == user_b_id)
            .all()
        }
        same_post_overlap = len(a_commented & b_commented)
    else:
        same_post_overlap = 0

    # 是否已有搭子关系
    has_social_match = (
        db.query(SocialMatch)
        .filter(
            (
                ((SocialMatch.user_id == user_a_id) & (SocialMatch.target_id == user_b_id))
                | ((SocialMatch.user_id == user_b_id) & (SocialMatch.target_id == user_a_id))
            ),
            SocialMatch.status.in_(["pending", "accepted"]),
        )
        .count()
        > 0
    )

    return {
        "comment_a_to_b": comment_a_to_b,
        "comment_b_to_a": comment_b_to_a,
        "like_a_to_b": like_a_to_b,
        "same_post_overlap": same_post_overlap,
        "has_social_match": has_social_match,
    }


# ── Phase 8A: Top-10 粗筛 + 会话管理 ─────────────────────────────────────────

def _score_all_atoa_candidates(
    db: Session,
    user_id: str,
    candidates: list[User],
    excluded_ids: set[str],
    dismissed_target_user_ids: set[str],
) -> list[dict]:
    """
    对所有 AtoA 候选批量规则评分（廉价，不调用 AI）。
    返回按 score 降序排列的列表，每项 {user, score, shared_topics, intent_type}。
    已在 excluded_ids 或 dismissed_target_user_ids 中的候选会被跳过。
    """
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return []

    card_a = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    inputs_a = _collect_match_keywords(db, user_id)
    scored: list[dict] = []

    for candidate in candidates:
        if candidate.id in excluded_ids:
            continue
        if candidate.id in dismissed_target_user_ids:
            continue

        card_b = db.query(AvatarCard).filter(AvatarCard.user_id == candidate.id).first()
        if not card_b or card_b.visibility == "private":
            continue

        # 规则预筛（不调用 AI）
        skip = _prefilter_atoa_pair(current_user, candidate, card_a, card_b, dismissed_target_user_ids)
        if skip:
            continue

        # 收集互动信号
        signals = _collect_interaction_signals_for_pair(db, user_id, candidate.id)

        # 规则打分（A 视角对 B）
        result = _rule_score_user_match(db, current_user, candidate, inputs_a, signals)
        base_score = result["score"] if result else 0

        # AtoA 互补加分（在规则分基础上叠加）
        atoa_bonus = 0
        if card_a and card_b:
            atoa_bonus += 10
        tags_a = set(str(t).lower() for t in _decode(card_a.interest_tags, [])) if card_a else set()
        tags_b = set(str(t).lower() for t in _decode(card_b.interest_tags, []))
        shared_topics = sorted(tags_a & tags_b)

        intents_a = set(str(t).lower() for t in _decode(card_a.social_intent, [])) if card_a else set()
        intents_b = set(str(t).lower() for t in _decode(card_b.social_intent, []))
        _intent_bonus_table = {
            ("buddy", "buddy"): 12, ("study", "study"): 10, ("dating", "dating"): 12,
            ("help", "buddy"): 10, ("buddy", "help"): 10,
            ("share", "share"): 8, ("sport", "sport"): 10,
        }
        for ia in intents_a:
            for ib in intents_b:
                bonus = _intent_bonus_table.get((ia, ib), 0)
                if bonus:
                    atoa_bonus += bonus
                    break

        score = min(base_score + atoa_bonus, 99)
        scored.append({
            "user": candidate,
            "score": score,
            "shared_topics": shared_topics,
            "intent_type": result["intent_type"] if result else "buddy",
            "reasons_a": result["reasons"] if result else [],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def _build_atoa_session(
    db: Session,
    user_id: str,
    scored_candidates: list[dict],
    surf_log_id: Optional[str] = None,
) -> AvatarAtoaSession:
    """
    创建新的 AtoaSession，记录 Top-N 候选和完整评分快照（含第11+位，用于补位）。
    若已有 active session 且仍有 pending_user_decision 的 interaction，则将旧的标记为 superseded 后再新建。
    """
    now = _now_ms()

    # 将旧的 active session 标记为 superseded
    old_sessions = (
        db.query(AvatarAtoaSession)
        .filter(AvatarAtoaSession.user_id == user_id, AvatarAtoaSession.status == "active")
        .all()
    )
    for old in old_sessions:
        old.status = "superseded"
        old.updated_at = now

    # 构建候选 ID 列表（Top-N）和完整评分快照
    top_n = scored_candidates[:_ATOA_TOP_N]
    all_cands = scored_candidates  # 含第11+位，供补位使用
    candidate_ids = [item["user"].id for item in top_n]
    score_snapshot = {item["user"].id: item["score"] for item in all_cands}

    session = AvatarAtoaSession(
        id=str(uuid4()),
        user_id=user_id,
        candidate_ids=_encode(candidate_ids),
        excluded_ids=_encode([]),
        score_snapshot=_encode(score_snapshot),
        status="active",
        surf_log_id=surf_log_id,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.flush()
    return session


def _get_replacement_candidate(
    db: Session,
    session: AvatarAtoaSession,
) -> Optional[User]:
    """
    从 session.score_snapshot 中找排名最高的、
    不在 session.excluded_ids 中、且尚无 AtoaInteraction 的候选。
    即取评分快照中第11、12...位里第一个未排除的候选。
    """
    snapshot: dict = _decode(session.score_snapshot, {})
    excluded: list = _decode(session.excluded_ids, [])
    candidate_ids: list = _decode(session.candidate_ids, [])

    # 已排除 + 已经在Top-10中的，都不补位
    skip_set = set(excluded) | set(candidate_ids)

    # 按评分降序遍历快照中的候选，找第一个可用的
    sorted_cands = sorted(snapshot.items(), key=lambda x: x[1], reverse=True)
    for user_id, _score in sorted_cands:
        if user_id in skip_set:
            continue
        # 检查该用户是否已有 interaction（任何 outcome）
        has_interaction = (
            db.query(AvatarAtoaInteraction)
            .filter(
                AvatarAtoaInteraction.user_a_id == session.user_id,
                AvatarAtoaInteraction.user_b_id == user_id,
                AvatarAtoaInteraction.session_id == session.id,
            )
            .first()
        ) is not None
        if has_interaction:
            continue
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user
    return None


def _apply_block_penalty(
    db: Session,
    user_a_id: str,
    user_b_id: str,
) -> None:
    """
    打断时双向降分：
    - A侧：将 A 的 AvatarMatch 中对 B 的记录降权（或写入 feedback_score -= PENALTY）
    - B侧：在 B 的所有对 A 的 AvatarMatch 中降低 match_score，使 A 下次不进 B 的 Top-10
    整个过程对 B 完全不可见。
    """
    # A 对 B 的记录降分
    match_ab = (
        db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_a_id,
            AvatarMatch.target_user_id == user_b_id,
        )
        .first()
    )
    if match_ab:
        match_ab.match_score = max(0, (match_ab.match_score or 0) - _ATOA_BLOCK_PENALTY)

    # B 对 A 的记录降分（B 看不到，仅影响下次粗筛排名）
    match_ba = (
        db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_b_id,
            AvatarMatch.target_user_id == user_a_id,
        )
        .first()
    )
    if match_ba:
        match_ba.match_score = max(0, (match_ba.match_score or 0) - _ATOA_BLOCK_PENALTY)


async def _simulate_atoa_conversation(
    card_a: AvatarCard,
    card_b: AvatarCard,
    max_rounds: int = 3,
    prior_conversation: Optional[list[dict]] = None,
) -> list[dict]:
    """
    【AtoA 核心】用 MiniMax 模拟两个分身之间的探针对话。
    每次最多产生 max_rounds 轮（1轮 = avatar_a + avatar_b 各一条消息，共 2 条）。
    prior_conversation: 非 None 时为续聊模式，AI 参考历史生成延续性对话。
    Mock 模式：根据 interest_tags 交集生成固定模板对话，不调用真实 API。
    """
    from app.ai.minimax_client import get_minimax_client
    from app.config import settings

    max_messages = max_rounds * 2  # 每轮 2 条消息
    tags_a: list[str] = _decode(card_a.interest_tags, [])
    tags_b: list[str] = _decode(card_b.interest_tags, [])
    shared = list(set(tags_a) & set(tags_b))
    intent_a = ", ".join(_decode(card_a.social_intent, [])[:2]) or "找搭子"
    intent_b = ", ".join(_decode(card_b.social_intent, [])[:2]) or "找搭子"
    is_continuation = bool(prior_conversation)

    if getattr(settings, "MINIMAX_MOCK", True):
        rounds: list[dict] = []
        topics = shared if shared else [intent_a]
        mock_templates = [
            (f"关于{topics[0]}，你平时怎么安排的？", f"我一般{topics[0]}这方面会花比较多时间，你呢？"),
            (f"听起来不错，我们可以多交流一下{topics[0]}相关的。", f"好啊，感觉我们在这方面挺有共鸣的。"),
            ("你有什么近期的计划吗？", "有的，我打算好好规划一下，希望能找到志同道合的朋友一起。"),
        ]
        start_idx = len(prior_conversation) // 2 if is_continuation else 0
        for i in range(min(max_rounds, len(mock_templates))):
            idx = (start_idx + i) % len(mock_templates)
            a_text, b_text = mock_templates[idx]
            if is_continuation and i == 0:
                a_text = f"继续上次的话题，{a_text}"
            rounds.append({"role": "avatar_a", "content": a_text})
            rounds.append({"role": "avatar_b", "content": b_text})
        return rounds[:max_messages]

    client = get_minimax_client()
    summary_a = (card_a.public_summary or "").strip()[:80]
    summary_b = (card_b.public_summary or "").strip()[:80]
    shared_str = "、".join(shared[:4]) if shared else "无明显交集"

    history_section = ""
    if is_continuation and prior_conversation:
        history_lines = []
        for turn in prior_conversation[-6:]:  # 最近 3 轮作为上下文
            role_label = "分身A" if turn["role"] == "avatar_a" else "分身B"
            history_lines.append(f"{role_label}：{turn['content']}")
        history_section = f"\n\n【已有对话历史（最近几轮）】\n" + "\n".join(history_lines) + "\n\n请在此基础上继续对话，保持连贯性。"

    prompt = f"""你需要模拟两个 AI 分身之间的对话（{"续聊" if is_continuation else "初次探路"}），生成 {max_rounds} 轮。

分身A 的人设：
- 公开简介：{summary_a or "暂无"}
- 兴趣标签：{", ".join(tags_a[:5])}
- 社交意图：{intent_a}

分身B 的人设：
- 公开简介：{summary_b or "暂无"}
- 兴趣标签：{", ".join(tags_b[:5])}
- 社交意图：{intent_b}

双方共同兴趣：{shared_str}{history_section}

规则：
1. 严格生成 {max_rounds} 轮（共 {max_rounds * 2} 条消息），分身A 先开口
2. 每条消息 1-2 句话，语气自然、不过于正式
3. 只使用名片上的公开信息，不涉及私密内容
4. 不替用户做任何承诺（如「我们加个微信吧」等）

请严格按以下JSON格式输出（共 {max_rounds * 2} 个元素，不要有任何额外文字）：
[
  {{"role": "avatar_a", "content": "..."}},
  {{"role": "avatar_b", "content": "..."}},
  ...
]"""

    # fallback_topic 在 Mock 分支外也需要可用
    fallback_topic = shared[0] if shared else intent_a

    try:
        raw = await client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_rounds * 150,
            temperature=0.75,
        )
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start != -1 and end > start:
            conversation = json.loads(raw[start:end])
            if isinstance(conversation, list) and len(conversation) >= 1:
                return conversation[:max_messages]
    except Exception:
        pass

    # 降级 fallback（API 调用失败或返回格式不符时使用）
    fallback = []
    for i in range(min(max_rounds, 3)):
        suffix = f"（续聊第{i+1}轮）" if is_continuation else ""
        fallback.append({"role": "avatar_a", "content": f"你好{suffix}，想多了解一下你的{fallback_topic}经历。"})
        fallback.append({"role": "avatar_b", "content": f"没问题，很高兴聊聊{fallback_topic}相关的话题。"})
    return fallback[:max_messages]


def _prefilter_atoa_pair(
    current_user: User,
    candidate: User,
    card_a: Optional[AvatarCard],
    card_b: Optional[AvatarCard],
    dismissed_target_user_ids: set[str],
) -> Optional[str]:
    """
    AtoA 规则预筛，通过返回 None，不通过返回跳过原因字符串。
    廉价快速，过不了不调用 AI。
    """
    if candidate.id in dismissed_target_user_ids:
        return "已 dismiss"
    if not card_a or not card_b:
        return "名片不完整"
    if card_b.visibility == "private":
        return "对方名片不可见"

    # 兴趣词最低重合
    tags_a = set(str(t).lower() for t in _decode(card_a.interest_tags, []))
    tags_b = set(str(t).lower() for t in _decode(card_b.interest_tags, []))
    if not tags_a.intersection(tags_b):
        return "无兴趣词重合"

    # 学校 only 过滤
    if getattr(candidate, "school_only", False):
        if (candidate.school or "") != (current_user.school or ""):
            return "school_only 限制"

    return None


async def _score_atoa_pair(
    db: Session,
    user_a: User,
    user_b: User,
    dismissed_target_user_ids: set[str],
) -> Optional[dict]:
    """
    AtoA 两步评估：规则预筛 → 分身对话 → 双向打分。
    返回 None 表示不值得写入（双方均低于下限，或预筛拒绝）。
    """
    card_a = db.query(AvatarCard).filter(AvatarCard.user_id == user_a.id).first()
    card_b = db.query(AvatarCard).filter(AvatarCard.user_id == user_b.id).first()

    # Step 1: 规则预筛
    skip_reason = _prefilter_atoa_pair(user_a, user_b, card_a, card_b, dismissed_target_user_ids)
    if skip_reason:
        return None

    # 收集双向互动信号
    raw_signals = _collect_interaction_signals_for_pair(db, user_a.id, user_b.id)

    # 计算分身名片兴趣词重合数，补充进信号字典（供 _rule_score_user_match 评分使用）
    tags_a_set = set(str(t).lower() for t in _decode(card_a.interest_tags, []))
    tags_b_set = set(str(t).lower() for t in _decode(card_b.interest_tags, []))
    interest_overlap_count = len(tags_a_set & tags_b_set)

    # 映射到 _rule_score_user_match 期望的 key 名称（A 视角）
    signals_ab = {
        "comment_to_them": raw_signals["comment_a_to_b"],
        "comment_to_me": raw_signals["comment_b_to_a"],
        "like_to_them": raw_signals["like_a_to_b"],
        "same_post_overlap": raw_signals["same_post_overlap"],
        "has_social_match": raw_signals["has_social_match"],
        "interest_overlap": interest_overlap_count,
    }
    # B 视角：方向翻转
    signals_ba = {
        "comment_to_them": raw_signals["comment_b_to_a"],
        "comment_to_me": raw_signals["comment_a_to_b"],
        "like_to_them": 0,
        "same_post_overlap": raw_signals["same_post_overlap"],
        "has_social_match": raw_signals["has_social_match"],
        "interest_overlap": interest_overlap_count,
    }

    inputs_a = _collect_match_keywords(db, user_a.id)
    inputs_b = _collect_match_keywords(db, user_b.id)

    result_ab = _rule_score_user_match(db, user_a, user_b, inputs_a, signals_ab)
    result_ba = _rule_score_user_match(db, user_b, user_a, inputs_b, signals_ba)

    score_ab = result_ab["score"] if result_ab else 0
    score_ba = result_ba["score"] if result_ba else 0

    # 双方均低于下限，不写入任何记录
    if score_ab < _ATOA_PREFILTER_THRESHOLD and score_ba < _ATOA_PREFILTER_THRESHOLD:
        return None

    # AtoA 互补加分
    atoa_bonus = 0
    tags_a = set(str(t).lower() for t in _decode(card_a.interest_tags, []))
    tags_b = set(str(t).lower() for t in _decode(card_b.interest_tags, []))
    shared_topics = sorted(tags_a & tags_b)

    if card_a and card_b:
        atoa_bonus += 10  # 双方都有名片

    intents_a = set(str(t).lower() for t in _decode(card_a.social_intent, []))
    intents_b = set(str(t).lower() for t in _decode(card_b.social_intent, []))
    mutual_intent_pairs = {
        ("buddy", "buddy"): 12, ("study", "study"): 10, ("dating", "dating"): 12,
        ("help", "buddy"): 10, ("buddy", "help"): 10,
        ("share", "share"): 8, ("sport", "sport"): 10,
    }
    for ia in intents_a:
        for ib in intents_b:
            pair_bonus = mutual_intent_pairs.get((ia, ib), 0)
            atoa_bonus += pair_bonus
            if pair_bonus:
                break

    score_ab = min(score_ab + atoa_bonus // 2, 99)
    score_ba = min(score_ba + atoa_bonus // 2, 99)

    # Step 2: 分身对话模拟（仅当任意一方 >= 预筛阈值时）
    conversation: list[dict] = []
    if score_ab >= _ATOA_PREFILTER_THRESHOLD or score_ba >= _ATOA_PREFILTER_THRESHOLD:
        try:
            conversation = await _simulate_atoa_conversation(card_a, card_b, max_rounds=3)
        except Exception:
            conversation = []

    reasons_ab = result_ab["reasons"] if result_ab else []
    reasons_ba = result_ba["reasons"] if result_ba else []
    intent_type = result_ab["intent_type"] if result_ab else (result_ba["intent_type"] if result_ba else "buddy")

    is_mutual = score_ab >= _ATOA_MUTUAL_THRESHOLD and score_ba >= _ATOA_MUTUAL_THRESHOLD

    if score_ab >= _ATOA_MUTUAL_THRESHOLD:
        # 双向达标 → mutual + 等待用户决策
        # 单向达标 → 仅 A 可见，也进入等待用户决策
        outcome = "mutual" if is_mutual else "pending_user_decision"
    else:
        outcome = "incompatible"

    return {
        "score_ab": score_ab,
        "score_ba": score_ba,
        "reasons_ab": reasons_ab,
        "reasons_ba": reasons_ba,
        "shared_topics": shared_topics,
        "conversation": conversation,
        "intent_type": intent_type,
        "is_mutual": is_mutual,
        "outcome": outcome,
        "risk_flags": [],
        "card_b_id": card_b.id if card_b else None,
    }


def _write_atoa_interaction(
    db: Session,
    user_a_id: str,
    user_b_id: str,
    score_data: dict,
    triggered_match_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AvatarAtoaInteraction:
    """
    写入或 upsert AvatarAtoaInteraction 探针日志。
    Phase 8A 新逻辑：outcome 固定为 "pending_user_decision"，is_visible_to_b 始终 False。
    不再自动设置 mutual/one_sided —— 由用户在 8C decide 接口触发。
    session_id：关联本次 Top-10 粗筛会话。
    """
    now = _now_ms()
    outcome = score_data.get("outcome", "pending_user_decision")

    # 若同一会话内已存在该对的记录则 upsert
    query = db.query(AvatarAtoaInteraction).filter(
        AvatarAtoaInteraction.user_a_id == user_a_id,
        AvatarAtoaInteraction.user_b_id == user_b_id,
    )
    if session_id:
        query = query.filter(AvatarAtoaInteraction.session_id == session_id)
    existing = query.first()

    if existing:
        existing.score_a = score_data.get("score_ab", 0)
        existing.score_b = score_data.get("score_ba", 0)
        existing.outcome = outcome
        existing.shared_topics = _encode(score_data.get("shared_topics", []))
        existing.reasons_a = _encode(score_data.get("reasons_ab", []))
        existing.reasons_b = _encode(score_data.get("reasons_ba", []))
        existing.risk_flags = _encode(score_data.get("risk_flags", []))
        existing.conversation = _encode(score_data.get("conversation", []))
        existing.is_visible_to_b = False
        if triggered_match_id:
            existing.triggered_match_id = triggered_match_id
        existing.updated_at = now
        return existing

    interaction = AvatarAtoaInteraction(
        id=str(uuid4()),
        initiator_id=user_a_id,
        session_id=session_id,
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        interaction_type="card_exchange",
        outcome=outcome,
        score_a=score_data.get("score_ab", 0),
        score_b=score_data.get("score_ba", 0),
        shared_topics=_encode(score_data.get("shared_topics", [])),
        reasons_a=_encode(score_data.get("reasons_ab", [])),
        reasons_b=_encode(score_data.get("reasons_ba", [])),
        risk_flags=_encode(score_data.get("risk_flags", [])),
        conversation=_encode(score_data.get("conversation", [])),
        triggered_match_id=triggered_match_id,
        is_visible_to_a=True,
        is_visible_to_b=False,
        interaction_phase=1,
        user_decision=None,
        created_at=now,
        updated_at=now,
    )
    db.add(interaction)
    return interaction


def _upsert_atoa_match_pair(
    db: Session,
    user_a_id: str,
    user_b_id: str,
    score_data: dict,
    interaction_id: str,
) -> Tuple[AvatarMatch, AvatarMatch]:
    """
    原子写入 A→B 和 B→A 两条 AvatarMatch(match_type='atoa')，通过 peer_match_id 互指。
    已存在则 upsert（更新分数和 is_mutual）。
    返回 (match_ab, match_ba)。
    """
    now = _now_ms()

    # 查找是否已存在 A→B
    existing_ab = (
        db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_a_id,
            AvatarMatch.target_user_id == user_b_id,
            AvatarMatch.match_type == "atoa",
        )
        .first()
    )
    # 查找是否已存在 B→A
    existing_ba = (
        db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_b_id,
            AvatarMatch.target_user_id == user_a_id,
            AvatarMatch.match_type == "atoa",
        )
        .first()
    )

    # 需要一个 anchor post（AtoA 匹配不依赖帖子，取对方最近一条帖子或留空）
    anchor_b = (
        db.query(PlazaPost)
        .filter(PlazaPost.user_id == user_b_id)
        .order_by(PlazaPost.created_at.desc())
        .first()
    )
    anchor_a = (
        db.query(PlazaPost)
        .filter(PlazaPost.user_id == user_a_id)
        .order_by(PlazaPost.created_at.desc())
        .first()
    )

    # 如果两人都没帖子，无法写入（post_id 非空约束）
    if not anchor_b or not anchor_a:
        # 创建占位（理论上不应发生，因为召回时会保证有帖子）
        return existing_ab, existing_ba  # type: ignore

    if existing_ab and existing_ab.status != "dismissed":
        existing_ab.match_score = score_data["score_ab"]
        existing_ab.their_score = score_data["score_ba"]
        existing_ab.match_reasons = _encode(score_data["reasons_ab"])
        existing_ab.their_reasons = _encode(score_data["reasons_ba"])
        existing_ab.is_mutual = True
        existing_ab.intent_type = score_data["intent_type"]
        existing_ab.target_avatar_card_id = score_data.get("card_b_id")
        match_ab = existing_ab
    else:
        match_ab_id = str(uuid4())
        match_ab = AvatarMatch(
            id=match_ab_id,
            user_id=user_a_id,
            post_id=anchor_b.id,
            target_user_id=user_b_id,
            match_score=score_data["score_ab"],
            their_score=score_data["score_ba"],
            match_reasons=_encode(score_data["reasons_ab"]),
            their_reasons=_encode(score_data["reasons_ba"]),
            agent_conversation=_encode(score_data["conversation"]),
            status="new",
            match_type="atoa",
            intent_type=score_data["intent_type"],
            risk_flags=_encode(score_data["risk_flags"]),
            is_mutual=True,
            target_avatar_card_id=score_data.get("card_b_id"),
            created_at=now,
        )
        db.add(match_ab)

    if existing_ba and existing_ba.status != "dismissed":
        existing_ba.match_score = score_data["score_ba"]
        existing_ba.their_score = score_data["score_ab"]
        existing_ba.match_reasons = _encode(score_data["reasons_ba"])
        existing_ba.their_reasons = _encode(score_data["reasons_ab"])
        existing_ba.is_mutual = True
        existing_ba.intent_type = score_data["intent_type"]
        existing_ba.target_avatar_card_id = score_data.get("card_b_id")
        match_ba = existing_ba
    else:
        match_ba_id = str(uuid4())
        match_ba = AvatarMatch(
            id=match_ba_id,
            user_id=user_b_id,
            post_id=anchor_a.id,
            target_user_id=user_a_id,
            match_score=score_data["score_ba"],
            their_score=score_data["score_ab"],
            match_reasons=_encode(score_data["reasons_ba"]),
            their_reasons=_encode(score_data["reasons_ab"]),
            agent_conversation=_encode(score_data["conversation"]),
            status="new",
            match_type="atoa",
            intent_type=score_data["intent_type"],
            risk_flags=_encode(score_data["risk_flags"]),
            is_mutual=True,
            target_avatar_card_id=score_data.get("card_b_id"),
            created_at=now,
        )
        db.add(match_ba)

    db.flush()  # 获取 ID 用于互指

    # 互指 peer_match_id
    match_ab.peer_match_id = match_ba.id
    match_ba.peer_match_id = match_ab.id

    return match_ab, match_ba


def _sync_atoa_mutual_flag(
    db: Session, match_id: str, new_is_mutual: bool
) -> None:
    """
    同步更新一对 AtoA 记录的 is_mutual 标志及对应 AtoaInteraction 的 outcome。
    通过 peer_match_id 找到对方记录一并更新。
    """
    match = db.query(AvatarMatch).filter(AvatarMatch.id == match_id).first()
    if not match or match.match_type != "atoa":
        return

    match.is_mutual = new_is_mutual
    new_outcome = "mutual" if new_is_mutual else "one_sided"

    # 同步 peer 记录
    if match.peer_match_id:
        peer = db.query(AvatarMatch).filter(AvatarMatch.id == match.peer_match_id).first()
        if peer:
            peer.is_mutual = new_is_mutual

    # 同步 AvatarAtoaInteraction
    interaction = (
        db.query(AvatarAtoaInteraction)
        .filter(
            AvatarAtoaInteraction.user_a_id == match.user_id,
            AvatarAtoaInteraction.user_b_id == match.target_user_id,
        )
        .first()
    )
    if interaction:
        interaction.outcome = new_outcome
        interaction.is_visible_to_b = new_is_mutual
        interaction.updated_at = _now_ms()


def generate_surf_report(
    atoa_scanned: int,
    atoa_mutual: int,
    atoa_one_sided: int,
    fallback_matches: int,
) -> str:
    """生成本次冲浪的 Agent 汇报摘要文案，写入 AvatarSurfLog.surf_report。"""
    parts: list[str] = []

    if atoa_scanned > 0:
        parts.append(f"分身今天为你找到了 {atoa_scanned} 位潜在搭子，已生成对话供你查看")
        if fallback_matches > 0:
            parts.append(f"还有 {fallback_matches} 条传统推荐")
    elif fallback_matches > 0:
        parts.append(f"分身今天为你匹配了 {fallback_matches} 条推荐")
    else:
        return "分身今天没有找到合适的候选，下次继续努力。"

    return "，".join(parts) + "。"


async def _refresh_matches_async(db: Session, user_id: str) -> dict:
    """
    Phase 8A 重构版：
    AtoA 主路径（Top-10 粗筛 → 会话 → 分身对话 → pending_user_decision）
    + 兜底通道（帖子型 / 用户型，对 auto_match_enabled=False 候选或 AtoA 冷启动时生效）

    返回统计字典供 run_avatar_surf_for_user 写入 SurfLog。
    """
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        return {"browsed": 0, "matched": 0, "atoa_scanned": 0, "atoa_mutual": 0,
                "atoa_one_sided": 0, "session_id": None}
    status = _get_or_create_status(db, user_id)
    if status.is_active is False:
        return {"browsed": 0, "matched": 0, "atoa_scanned": 0, "atoa_mutual": 0,
                "atoa_one_sided": 0, "session_id": None}

    inputs = _collect_match_keywords(db, user_id)
    enabled_channels = _decode(status.enabled_channels, ["buddy", "help", "share", "dating"])
    dismissed_post_ids: set[str] = {
        item.post_id
        for item in db.query(AvatarMatch)
        .filter(AvatarMatch.user_id == user_id, AvatarMatch.status == "dismissed")
        .all()
    }
    dismissed_target_user_ids: set[str] = {
        item.target_user_id
        for item in db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_id,
            AvatarMatch.status == "dismissed",
            AvatarMatch.target_user_id != None,  # noqa: E711
        )
        .all()
    }
    # 通过 AtoaInteraction.blocked 得到的排除集合（打断过的用户）
    blocked_user_ids: set[str] = {
        row.user_b_id
        for row in db.query(AvatarAtoaInteraction.user_b_id)
        .filter(
            AvatarAtoaInteraction.user_a_id == user_id,
            AvatarAtoaInteraction.outcome == "blocked",
        )
        .all()
    }
    excluded_ids = dismissed_target_user_ids | blocked_user_ids

    browsed_count = 0
    matched_count = 0
    atoa_scanned = 0
    session_id: Optional[str] = None
    now = _now_ms()

    # ── AtoA 主路径（Phase 8A Top-10 搭子模式）────────────────────────────────
    atoa_enabled_globally = (
        db.query(AvatarStatus)
        .filter(
            AvatarStatus.user_id != user_id,
            AvatarStatus.is_active == True,  # noqa: E712
            AvatarStatus.auto_match_enabled == True,  # noqa: E712
        )
        .count()
        >= _ATOA_COLD_START_MIN_USERS
    )

    if atoa_enabled_globally and status.auto_match_enabled:
        # 1. 召回所有 AtoA 候选
        all_atoa_candidates = _recall_atoa_candidates(db, user_id)

        # 2. 批量规则评分（廉价，不调用 AI）
        scored = _score_all_atoa_candidates(
            db, user_id, all_atoa_candidates, excluded_ids, dismissed_target_user_ids
        )

        if scored:
            # 3. 建立 Top-10 会话（存储 candidate_ids + 完整 score_snapshot）
            session = _build_atoa_session(db, user_id, scored)
            session_id = session.id
            db.flush()

            top10 = scored[:_ATOA_TOP_N]
            atoa_scanned = len(top10)

            # 4. 对每位 Top-10 候选：规则预筛 → AI 分身对话 → 写 AtoaInteraction
            card_a = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
            for item in top10:
                candidate: User = item["user"]
                card_b = db.query(AvatarCard).filter(AvatarCard.user_id == candidate.id).first()

                # 规则预筛（不调用 AI）
                skip = _prefilter_atoa_pair(
                    current_user, candidate, card_a, card_b, excluded_ids
                )
                if skip:
                    atoa_scanned -= 1
                    continue

                # 生成分身对话（AI，最多 3 轮）
                conversation: list[dict] = []
                if card_a and card_b:
                    try:
                        conversation = await _simulate_atoa_conversation(card_a, card_b, max_rounds=3)
                    except Exception:
                        conversation = []

                # 收集双向信号（用于写入 reasons_ba）
                signals_ab = _collect_interaction_signals_for_pair(db, user_id, candidate.id)
                signals_ba = {
                    "comment_a_to_b": signals_ab["comment_b_to_a"],
                    "comment_b_to_a": signals_ab["comment_a_to_b"],
                    "like_a_to_b": 0,
                    "same_post_overlap": signals_ab["same_post_overlap"],
                    "has_social_match": signals_ab["has_social_match"],
                }
                inputs_b = _collect_match_keywords(db, candidate.id)
                result_ba = _rule_score_user_match(db, candidate, current_user, inputs_b, signals_ba)

                score_data = {
                    "outcome": "pending_user_decision",
                    "score_ab": item["score"],
                    "score_ba": result_ba["score"] if result_ba else 0,
                    "shared_topics": item["shared_topics"],
                    "reasons_ab": item["reasons_a"],
                    "reasons_ba": result_ba["reasons"] if result_ba else [],
                    "risk_flags": [],
                    "conversation": conversation,
                    "intent_type": item["intent_type"],
                    "is_mutual": False,
                }

                _write_atoa_interaction(
                    db, user_id, candidate.id, score_data,
                    session_id=session_id
                )
                db.flush()

            db.commit()

    # ── 帖子通道（兜底，始终运行以保证推荐列表不为空）────────────────────────
    rows = (
        db.query(PlazaPost, User)
        .join(User, PlazaPost.user_id == User.id)
        .filter(PlazaPost.user_id != user_id, PlazaPost.type.in_(enabled_channels))
        .order_by(PlazaPost.created_at.desc())
        .limit(60)
        .all()
    )

    for post, author in rows:
        if post.id in dismissed_post_ids:
            continue
        if post.school_only and (author.school or "") != (current_user.school or ""):
            continue
        browsed_count += 1
        match_data = _build_match_for_post(db, current_user, post, author, inputs)
        if not match_data:
            continue
        matched_count += 1
        existing = (
            db.query(AvatarMatch)
            .filter(
                AvatarMatch.user_id == user_id,
                AvatarMatch.post_id == post.id,
                AvatarMatch.match_type == "post",
            )
            .first()
        )
        if not existing:
            db.add(AvatarMatch(
                id=str(uuid4()),
                user_id=user_id,
                post_id=post.id,
                match_score=match_data["score"],
                match_reasons=_encode(match_data["reasons"]),
                agent_conversation=_encode(match_data["agent_conversation"]),
                status="new",
                match_type="post",
                intent_type="buddy",
                created_at=now,
            ))
        elif existing.status != "dismissed":
            existing.match_score = match_data["score"]
            existing.match_reasons = _encode(match_data["reasons"])
            existing.agent_conversation = _encode(match_data["agent_conversation"])

    # ── 用户通道（Phase 5 兜底）──────────────────────────────────────────────
    user_candidates = _recall_user_candidates(db, user_id, current_user, inputs)
    for candidate, signals in user_candidates:
        if candidate.id in excluded_ids:
            continue
        score_data_u = _rule_score_user_match(db, current_user, candidate, inputs, signals)
        if not score_data_u:
            continue

        anchor_post = (
            db.query(PlazaPost)
            .filter(PlazaPost.user_id == candidate.id, PlazaPost.type.in_(enabled_channels))
            .order_by(PlazaPost.created_at.desc())
            .first()
        )
        if not anchor_post:
            continue

        browsed_count += 1
        matched_count += 1

        existing = (
            db.query(AvatarMatch)
            .filter(
                AvatarMatch.user_id == user_id,
                AvatarMatch.target_user_id == candidate.id,
                AvatarMatch.match_type == "user",
            )
            .first()
        )
        if not existing:
            db.add(AvatarMatch(
                id=str(uuid4()),
                user_id=user_id,
                post_id=anchor_post.id,
                target_user_id=candidate.id,
                match_score=score_data_u["score"],
                match_reasons=_encode(score_data_u["reasons"]),
                agent_conversation=_encode([]),
                status="new",
                match_type="user",
                intent_type=score_data_u["intent_type"],
                created_at=now,
            ))
        elif existing.status != "dismissed":
            existing.match_score = score_data_u["score"]
            existing.match_reasons = _encode(score_data_u["reasons"])
            existing.intent_type = score_data_u["intent_type"]
            existing.post_id = anchor_post.id

    status.browsed_count = max(status.browsed_count or 0, browsed_count)
    status.matched_count = matched_count
    status.last_active_at = now
    db.commit()

    return {
        "browsed": browsed_count,
        "matched": matched_count,
        "atoa_scanned": atoa_scanned,
        "atoa_mutual": 0,        # Phase 8A：不自动判断 mutual，由用户决定
        "atoa_one_sided": 0,
        "session_id": session_id,
    }


def _refresh_matches(db: Session, user_id: str) -> None:
    """
    同步兼容包装器（供 list_matches 等同步路径调用，不含 AtoA 通道）。
    AtoA 通道需要 async，只能由 run_avatar_surf_for_user（async）触发。
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_refresh_matches_async(db, user_id))
    except RuntimeError:
        asyncio.run(_refresh_matches_async(db, user_id))


def list_matches(db: Session, user_id: str) -> List[dict]:
    """分身推荐列表，排除 dismissed，按 match_score DESC（含帖子型 + 用户型匹配）"""
    _refresh_matches(db, user_id)

    # 查询所有未 dismissed 的匹配，附带帖子和帖子作者
    rows = (
        db.query(AvatarMatch, PlazaPost, User)
        .join(PlazaPost, AvatarMatch.post_id == PlazaPost.id)
        .join(User, PlazaPost.user_id == User.id)
        .filter(AvatarMatch.user_id == user_id)
        .filter(AvatarMatch.status != "dismissed")
        .order_by(AvatarMatch.match_score.desc())
        .all()
    )

    result = []
    for match, post, post_author in rows:
        # 用户型匹配额外附上目标用户信息
        target_user_info = None
        if match.match_type == "user" and match.target_user_id:
            tu = db.query(User).filter(User.id == match.target_user_id).first()
            if tu:
                target_user_info = {
                    "id": tu.id,
                    "name": tu.name or tu.username,
                    "avatar": tu.avatar or "",
                    "school": tu.school or "",
                    "major": tu.major or "",
                    "grade": tu.grade or "",
                }

        result.append({
            "id": match.id,
            "post_id": match.post_id,
            "post": _post_to_dict(post, post_author),
            "match_score": match.match_score or 0,
            "match_reasons": _decode(match.match_reasons, []),
            "agent_conversation": _decode(match.agent_conversation, []),
            "status": match.status or "new",
            "created_at": match.created_at,
            # Phase 5 新字段
            "match_type": match.match_type or "post",
            "intent_type": match.intent_type or "buddy",
            "target_user": target_user_info,
            # Phase 6 新字段
            "suggested_opening": match.suggested_opening or "",
            "ai_refined": match.ai_refined or False,
            "risk_flags": _decode(match.risk_flags, []),
        })
    return result


# ==================== 分身行动草稿/审批 ====================

def list_actions(db: Session, user_id: str, status: Optional[str] = None) -> List[dict]:
    query = db.query(AgentAction).filter(AgentAction.user_id == user_id)
    if status:
        query = query.filter(AgentAction.status == status)
    actions = query.order_by(AgentAction.created_at.desc()).limit(100).all()
    return [_action_to_dict(action) for action in actions]


async def create_plaza_comment_draft(
    db: Session,
    current_user: User,
    post_id: str,
    parent_comment_id: Optional[str] = None,
    input_context_extra: Optional[dict] = None,
) -> dict:
    """生成广场分身评论草稿，不直接发布。"""
    from app.ai.minimax_client import get_minimax_client
    from app.memory.prompts import format_memory_context
    from app.memory.retriever import retrieve_memories

    post = db.query(PlazaPost).filter(PlazaPost.id == post_id).first()
    if not post:
        raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)
    if not post.allow_agent_reply:
        raise ApiException(code=PARAM_INVALID, message="该帖子不允许分身回复", status_code=400)

    parent_comment = None
    parent_user = None
    if parent_comment_id:
        row = (
            db.query(PlazaComment, User)
            .join(User, PlazaComment.user_id == User.id)
            .filter(PlazaComment.id == parent_comment_id, PlazaComment.post_id == post_id)
            .first()
        )
        if not row:
            raise ApiException(code=NOT_FOUND, message="要回复的评论不存在", status_code=404)
        parent_comment, parent_user = row

    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == current_user.id).first()
    if not profile or not (profile.summary or "").strip():
        raise ApiException(code=PARAM_INVALID, message="请先生成分身侧写", status_code=400)

    memories = retrieve_memories(
        db,
        user_id=current_user.id,
        query=post.content or "",
        scenario="avatar_comment",
        top_k=8,
        source_types=["diary", "chat_session", "plaza_post", "plaza_comment", "social_message", "material"],
    )
    memory_context = format_memory_context(memories, scenario="avatar_comment") or "暂无"

    system_prompt = (
        "你是用户的 AI 分身，负责生成广场评论草稿。"
        "评论要像用户本人可能会说的话，自然、友善、低压力。"
        "不要暴露自己是 AI，不要泄露日记、私聊、AI 对话等私密原文。"
    )
    parent_context = ""
    if parent_comment:
        parent_author_name = parent_user.name or parent_user.username if parent_user else "对方"
        if parent_comment.is_agent:
            parent_author_name = f"{parent_author_name}的分身"
        parent_context = f"\n【你正在回复的评论】{parent_author_name}：{parent_comment.content}\n"

    user_prompt = (
        f"【用户侧写】\n{profile.summary}\n\n"
        f"【相关长期记忆（仅供理解，不可原文外泄）】\n{memory_context}\n\n"
        f"【帖子类型】{post.type}\n"
        f"【帖子内容】{post.content}\n\n"
        f"{parent_context}"
        "请生成 1-3 句话的评论草稿，只输出评论正文。"
    )
    client = get_minimax_client()
    reply = await client.chat_completion(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.85,
    )
    reply = reply.strip().strip('"').strip("'")
    now = _now_ms()
    action = AgentAction(
        id=str(uuid4()),
        user_id=current_user.id,
        agent_id="default-avatar",
        action_type="comment_post",
        target_type="plaza_post",
        target_id=post.id,
        input_context=_encode(
            {
                "post_id": post.id,
                "post_type": post.type,
                "memory_count": len(memories),
                "parent_comment_id": parent_comment_id,
                **(input_context_extra or {}),
            }
        ),
        output_text=reply,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return _action_to_dict(action)


def approve_action(db: Session, user_id: str, action_id: str) -> dict:
    """批准分身行动。当前支持发布广场评论草稿。"""
    action = db.query(AgentAction).filter(AgentAction.id == action_id, AgentAction.user_id == user_id).first()
    if not action:
        raise ApiException(code=NOT_FOUND, message="分身行动不存在", status_code=404)
    if action.status != "draft":
        raise ApiException(code=PARAM_INVALID, message="该分身行动不是待审批状态", status_code=400)

    now = _now_ms()
    if action.action_type == "comment_post" and action.target_type == "plaza_post":
        post = db.query(PlazaPost).filter(PlazaPost.id == action.target_id).first()
        if not post:
            raise ApiException(code=NOT_FOUND, message="帖子不存在", status_code=404)
        input_context = _decode(action.input_context, {})
        parent_comment_id = input_context.get("parent_comment_id") or None
        if parent_comment_id:
            parent = db.query(PlazaComment).filter(
                PlazaComment.id == parent_comment_id,
                PlazaComment.post_id == post.id,
            ).first()
            if not parent:
                raise ApiException(code=NOT_FOUND, message="要回复的评论不存在", status_code=404)
        comment = PlazaComment(
            id=str(uuid4()),
            post_id=post.id,
            user_id=user_id,
            parent_comment_id=parent_comment_id,
            content=action.output_text,
            is_agent=True,
            created_at=now,
        )
        db.add(comment)
        post.comments = (post.comments or 0) + 1
        post.agent_responses = (post.agent_responses or 0) + 1
        action.status = "published"
        action.updated_at = now
        db.commit()
        db.refresh(action)
        from app.memory.ingestion import ingest_plaza_comment

        ingest_plaza_comment(db, comment)
        # Phase 3：批准评论草稿 → 正向反馈 +4
        update_bandit_feedback(db, user_id, 4.0)
        return _action_to_dict(action)

    raise ApiException(code=PARAM_INVALID, message="暂不支持该分身行动类型", status_code=400)


def reject_action(db: Session, user_id: str, action_id: str) -> dict:
    action = db.query(AgentAction).filter(AgentAction.id == action_id, AgentAction.user_id == user_id).first()
    if not action:
        raise ApiException(code=NOT_FOUND, message="分身行动不存在", status_code=404)
    if action.status != "draft":
        raise ApiException(code=PARAM_INVALID, message="该分身行动不是待审批状态", status_code=400)
    action.status = "rejected"
    action.updated_at = _now_ms()
    db.commit()
    db.refresh(action)
    # Phase 3：拒绝草稿 → 负向反馈 -2
    update_bandit_feedback(db, user_id, -2.0)
    return _action_to_dict(action)


async def auto_surf_comments(db: Session, current_user: User, limit: int = 1) -> dict:
    """触发一次分身冲浪：按匹配度、开关和频率限制自动生成评论草稿或直接发布。"""
    status_obj = _get_or_create_status(db, current_user.id)
    status = _status_to_dict(status_obj)
    enabled_actions = status.get("enabled_actions", [])
    settings = status.get("match_range", {})
    if status_obj.is_active is False:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "分身当前未开启"}
    if "comment" not in enabled_actions or "auto_surf_comment" not in enabled_actions:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "未开启自动冲浪回复"}

    now = _now_ms()
    start_of_day = now - (now + 8 * 60 * 60 * 1000) % (24 * 60 * 60 * 1000)
    daily_limit = int(settings.get("autoReplyDailyLimit") or 5)
    interval_ms = int(settings.get("autoReplyIntervalMinutes") or 30) * 60 * 1000
    min_score = int(settings.get("autoReplyMinScore") or 55)
    safe_limit = max(1, min(int(limit or 1), 5))

    today_count = (
        db.query(AgentAction)
        .filter(
            AgentAction.user_id == current_user.id,
            AgentAction.action_type == "comment_post",
            AgentAction.created_at >= start_of_day,
        )
        .count()
    )
    if today_count >= daily_limit:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "已达到今日自动回复上限"}

    latest = (
        db.query(AgentAction)
        .filter(AgentAction.user_id == current_user.id, AgentAction.action_type == "comment_post")
        .order_by(AgentAction.created_at.desc())
        .first()
    )
    if latest and interval_ms > 0 and now - (latest.created_at or 0) < interval_ms:
        return {"actions": [], "published_count": 0, "draft_count": 0, "skipped_reason": "距离上次回复太近，已按频率限制跳过"}

    matches = list_matches(db, current_user.id)
    actions: list[dict] = []
    published_count = 0
    draft_count = 0
    for match in matches:
        if len(actions) >= safe_limit or today_count + len(actions) >= daily_limit:
            break
        if int(match.get("match_score") or 0) < min_score:
            continue
        post = match.get("post") or {}
        post_id = post.get("id") or match.get("post_id")
        if not post_id or not post.get("allow_agent_reply", True):
            continue
        existing = (
            db.query(AgentAction)
            .filter(
                AgentAction.user_id == current_user.id,
                AgentAction.action_type == "comment_post",
                AgentAction.target_id == post_id,
                AgentAction.status.in_(["draft", "published"]),
            )
            .first()
        )
        if existing:
            continue
        action = await create_plaza_comment_draft(
            db,
            current_user,
            post_id,
            input_context_extra={
                "auto_surf": True,
                "match_id": match.get("id"),
                "match_score": match.get("match_score"),
                "match_reasons": match.get("match_reasons", []),
            },
        )
        if "auto_approve_comment" in enabled_actions:
            action = approve_action(db, current_user.id, action["id"])
            published_count += 1
        else:
            draft_count += 1
        actions.append(action)

    skipped = "" if actions else "没有找到达到兴趣阈值且未回复过的帖子"
    return {
        "actions": actions,
        "published_count": published_count,
        "draft_count": draft_count,
        "skipped_reason": skipped,
    }


# ==================== 分身侧写 ====================

def _profile_to_dict(p: AvatarProfile) -> dict:
    """AvatarProfile ORM → 响应字典"""
    return {
        "summary": p.summary or "",
        "diary_count": p.diary_count or 0,
        "chat_count": p.chat_count or 0,
        "generated_at": p.generated_at or 0,
    }


def _card_to_dict(card: AvatarCard) -> dict:
    return {
        "display_name": card.display_name or "",
        "public_summary": card.public_summary or "",
        "interest_tags": _decode(card.interest_tags, []),
        "social_intent": _decode(card.social_intent, []),
        "conversation_style": _decode(card.conversation_style, {}),
        "boundaries": _decode(card.boundaries, []),
        "visibility": card.visibility or "private",
        "updated_at": card.updated_at or 0,
    }


def _action_to_dict(action: AgentAction) -> dict:
    return {
        "id": action.id,
        "action_type": action.action_type or "",
        "target_type": action.target_type or "",
        "target_id": action.target_id or "",
        "input_context": _decode(action.input_context, {}),
        "output_text": action.output_text or "",
        "status": action.status or "draft",
        "created_at": action.created_at or 0,
        "updated_at": action.updated_at or 0,
    }


def get_profile(db: Session, user_id: str) -> dict:
    """获取分身侧写，不存在返回默认空侧写"""
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    if not profile:
        return {"summary": "", "diary_count": 0, "chat_count": 0, "generated_at": 0}
    return _profile_to_dict(profile)


def get_avatar_card(db: Session, user_id: str) -> dict:
    """获取分身名片，不存在返回空名片。"""
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    if not card:
        return {
            "display_name": "",
            "public_summary": "",
            "interest_tags": [],
            "social_intent": [],
            "conversation_style": {},
            "boundaries": [],
            "visibility": "private",
            "updated_at": 0,
        }
    return _card_to_dict(card)


def regenerate_avatar_card(db: Session, user_id: str) -> dict:
    """基于当前画像和结构化记忆生成一个保守的分身名片。"""
    user = db.query(User).filter(User.id == user_id).first()
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id, MemoryFact.is_active == True)  # noqa: E712
        .order_by(MemoryFact.is_pinned.desc(), MemoryFact.updated_at.desc())
        .limit(50)
        .all()
    )
    interests = []
    boundaries = []
    intents = []
    for fact in facts:
        text = (fact.content or "").strip()
        if not text:
            continue
        if fact.category in {"interest", "preference", "habit"} and len(interests) < 12:
            interests.append(text[:24])
        elif fact.category == "boundary" and len(boundaries) < 6:
            boundaries.append(text[:60])
        elif fact.category == "need" and len(intents) < 6:
            intents.append(text[:40])

    summary = (profile.summary if profile else "") or ""
    public_summary = summary[:160] if summary else "这个分身还在学习主人的兴趣和社交偏好。"
    now = _now_ms()
    card = db.query(AvatarCard).filter(AvatarCard.user_id == user_id).first()
    if not card:
        card = AvatarCard(
            id=str(uuid4()),
            user_id=user_id,
            display_name=f"{(user.name or user.username) if user else '我'}的分身",
            public_summary=public_summary,
            interest_tags=_encode(interests),
            social_intent=_encode(intents),
            conversation_style=_encode({"tone": "自然、友善、低压力"}),
            boundaries=_encode(boundaries),
            visibility="private",
            updated_at=now,
        )
        db.add(card)
    else:
        card.display_name = card.display_name or f"{(user.name or user.username) if user else '我'}的分身"
        card.public_summary = public_summary
        card.interest_tags = _encode(interests)
        card.social_intent = _encode(intents)
        card.conversation_style = _encode({"tone": "自然、友善、低压力"})
        card.boundaries = _encode(boundaries)
        card.updated_at = now
    db.commit()
    db.refresh(card)
    return _card_to_dict(card)


async def regenerate_profile(db: Session, user_id: str) -> dict:
    """重新生成分身侧写：读取记忆+日记+聊天 → 调用 AI 生成摘要"""
    from app.models.diary import Diary
    from app.models.chat import ChatMessage
    from app.models.memory import MemoryDocument
    from app.ai.minimax_client import get_minimax_client

    # 收集用户记忆
    memories = (
        db.query(AvatarMemory)
        .filter(AvatarMemory.user_id == user_id, AvatarMemory.is_active == True)  # noqa: E712
        .order_by(AvatarMemory.created_at.desc())
        .limit(50)
        .all()
    )
    memory_text = "\n".join([
        f"- [{m.category}] {m.content}" for m in memories
    ]) if memories else "暂无记忆"

    # 统一记忆系统中的相关原文证据，优先作为新侧写依据。
    try:
        from app.memory.prompts import format_memory_context
        from app.memory.retriever import retrieve_memories

        retrieved_memories = retrieve_memories(
            db,
            user_id=user_id,
            query="用户的性格 兴趣 生活习惯 社交偏好 写作风格 近期状态",
            scenario="profile_generation",
            top_k=30,
            source_types=["diary", "chat_session", "plaza_post", "plaza_comment", "social_message", "material"],
        )
        retrieved_memory_text = format_memory_context(retrieved_memories, scenario="profile_generation")
    except Exception:
        retrieved_memory_text = ""

    # 收集近期日记（最近 10 篇）
    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user_id)
        .order_by(Diary.created_at.desc())
        .limit(10)
        .all()
    )
    diary_count = len(diaries)
    diary_text = "\n".join([
        f"- {d.title or '无标题'}: {(d.content or '')[:100]}" for d in diaries
    ]) if diaries else "暂无日记"

    # 收集近期聊天（最近 30 条）
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.role == "user")
        .order_by(ChatMessage.timestamp.desc())
        .limit(30)
        .all()
    )
    chat_count = len(messages)
    chat_text = "\n".join([
        f"- {msg.content[:80]}" for msg in messages
    ]) if messages else "暂无对话"
    memory_doc_count = (
        db.query(MemoryDocument)
        .filter(MemoryDocument.user_id == user_id, MemoryDocument.is_deleted == False)  # noqa: E712
        .count()
    )

    # 调用 AI 生成侧写
    system_prompt = (
        "你是一个用户画像分析师。根据用户的记忆库、日记摘要和聊天记录，"
        "生成一段简洁的人格侧写（150-300字），描述用户的性格特征、兴趣爱好、"
        "社交偏好和生活习惯。语言要自然温暖，像朋友之间的了解。"
    )
    user_prompt = (
        f"【统一长期记忆检索结果】\n{retrieved_memory_text or '暂无长期记忆检索结果'}\n\n"
        f"【手动/结构化记忆库】\n{memory_text}\n\n"
        f"【近期日记摘要】\n{diary_text}\n\n"
        f"【近期聊天内容】\n{chat_text}\n\n"
        "请基于以上信息生成用户人格侧写："
    )

    client = get_minimax_client()
    summary = await client.chat_completion(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.7,
    )

    # 写入/更新 avatar_profiles 表
    now = _now_ms()
    profile = db.query(AvatarProfile).filter(AvatarProfile.user_id == user_id).first()
    if profile:
        profile.summary = summary
        profile.diary_count = diary_count
        profile.chat_count = chat_count or memory_doc_count
        profile.generated_at = now
    else:
        profile = AvatarProfile(
            id=str(uuid4()),
            user_id=user_id,
            summary=summary,
            diary_count=diary_count,
            chat_count=chat_count or memory_doc_count,
            generated_at=now,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return _profile_to_dict(profile)


# ==================== Phase 8A: 用户监察接口 ====================

def _latest_success_surf_log(db: Session, user_id: str) -> Optional[AvatarSurfLog]:
    """最近一次成功的分身冲浪日志（按 started_at）。"""
    return (
        db.query(AvatarSurfLog)
        .filter(
            AvatarSurfLog.user_id == user_id,
            AvatarSurfLog.status == "success",
        )
        .order_by(AvatarSurfLog.started_at.desc())
        .first()
    )


def _latest_top10_session_id_from_surf(db: Session, user_id: str) -> Optional[str]:
    """最近一次成功冲浪关联的 AtoaSession.id（无 AtoA 时为 None）。"""
    log = _latest_success_surf_log(db, user_id)
    if not log or not log.top10_session_id:
        return None
    return log.top10_session_id


def get_probe_log(
    db: Session,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
    outcome: Optional[str] = None,
    session_id: Optional[str] = None,
) -> list[dict]:
    """
    返回我的分身发起的 AtoA 探针日志。

    默认：仅 **最近一次成功冲浪** 对应的 `top10_session_id` 下，
    每个对方用户（user_b）只保留 **最新一条** 互动（按 created_at）。

    若传入 `session_id`，则查看该次会话（便于核对历史），规则同上（按 user_b 去重）。
    """
    target_sid = session_id if session_id else _latest_top10_session_id_from_surf(db, user_id)
    if not target_sid:
        return []

    query = db.query(AvatarAtoaInteraction).filter(
        AvatarAtoaInteraction.user_a_id == user_id,
        AvatarAtoaInteraction.is_visible_to_a == True,  # noqa: E712
        AvatarAtoaInteraction.session_id == target_sid,
    )
    if outcome:
        query = query.filter(AvatarAtoaInteraction.outcome == outcome)

    rows = query.order_by(AvatarAtoaInteraction.created_at.desc()).all()

    # 同一 session、同一 user_b 可能有多条（多次冲浪重复探针）；只保留最新一条
    seen_b: set[str] = set()
    deduped: list[AvatarAtoaInteraction] = []
    for row in rows:
        if row.user_b_id in seen_b:
            continue
        seen_b.add(row.user_b_id)
        deduped.append(row)

    rows = deduped[offset : offset + limit]

    _outcome_labels = {
        "pending_user_decision": "等待你的决定",
        "blocked": "已打断",
        "connected": "已发出结交申请",
        "connect_confirmed": "已成为搭子",
        "connect_rejected": "对方拒绝了申请",
        "mutual": "双向达标",
        "one_sided": "单向感兴趣",
        "incompatible": "不匹配",
    }

    result = []
    for row in rows:
        other = db.query(User).filter(User.id == row.user_b_id).first()
        result.append({
            "id": row.id,
            "session_id": row.session_id,
            "user_b_id": row.user_b_id,
            "user_b_name": (other.name or other.username) if other else "",
            "user_b_avatar": (other.avatar or "") if other else "",
            "interaction_type": row.interaction_type,
            "outcome": row.outcome,
            "readable_outcome": _outcome_labels.get(row.outcome or "", row.outcome or ""),
            "score_a": row.score_a,
            "score_b": row.score_b,
            "shared_topics": _decode(row.shared_topics, []),
            "reasons_a": _decode(row.reasons_a, []),
            "conversation": _decode(row.conversation, []),
            "risk_flags": _decode(row.risk_flags, []),
            "interaction_phase": row.interaction_phase or 1,
            "user_decision": row.user_decision,
            "is_mutual": row.outcome == "mutual",
            "triggered_match_id": row.triggered_match_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        })
    return result


def get_atoa_sessions(
    db: Session,
    user_id: str,
    limit: int = 5,
    offset: int = 0,
) -> list[dict]:
    """
    仅返回 **最近一次成功冲浪** 对应的 Top-10 会话（0 或 1 条）。

    统计口径：同一 session 内按 user_b 去重后再计 pending / decided；
    candidate_count 为粗筛候选人数（candidate_ids 长度）。
    """
    sid = _latest_top10_session_id_from_surf(db, user_id)
    if not sid:
        return []

    s = db.query(AvatarAtoaSession).filter(AvatarAtoaSession.id == sid).first()
    if not s or s.user_id != user_id:
        return []

    candidate_ids: list[str] = _decode(s.candidate_ids, [])
    excluded_ids: list[str] = _decode(s.excluded_ids, [])

    interactions = (
        db.query(AvatarAtoaInteraction)
        .filter(AvatarAtoaInteraction.session_id == s.id)
        .order_by(AvatarAtoaInteraction.created_at.desc())
        .all()
    )
    # 每个 user_b 只保留最新一条互动，再统计 outcome
    seen_b: set[str] = set()
    distinct_latest: list[AvatarAtoaInteraction] = []
    for intr in interactions:
        if intr.user_b_id in seen_b:
            continue
        seen_b.add(intr.user_b_id)
        distinct_latest.append(intr)

    outcome_counts: dict[str, int] = {}
    for intr in distinct_latest:
        outcome_counts[intr.outcome or ""] = outcome_counts.get(intr.outcome or "", 0) + 1

    pending_count = outcome_counts.get("pending_user_decision", 0)
    decided_count = sum(
        v for k, v in outcome_counts.items() if k != "pending_user_decision"
    )

    row = {
        "id": s.id,
        "status": s.status,
        "candidate_count": len(candidate_ids),
        "excluded_count": len(excluded_ids),
        "pending_count": pending_count,
        "decided_count": decided_count,
        "surf_log_id": s.surf_log_id,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }
    # offset/limit：仅一条时 offset=0 仍可用；offset>=1 则视为翻页无数据
    if offset > 0:
        return []
    if limit <= 0:
        return []
    return [row]


def get_mutual_matches(
    db: Session,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """
    返回当前用户的全部 AtoA mutual 匹配（双向达标，is_mutual=True）。
    供「分身推荐 - 双向匹配」专栏展示。
    """
    rows = (
        db.query(AvatarMatch)
        .filter(
            AvatarMatch.user_id == user_id,
            AvatarMatch.match_type == "atoa",
            AvatarMatch.is_mutual == True,  # noqa: E712
            AvatarMatch.status != "dismissed",
        )
        .order_by(AvatarMatch.match_score.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for m in rows:
        target = db.query(User).filter(User.id == m.target_user_id).first()
        target_card = (
            db.query(AvatarCard).filter(AvatarCard.user_id == m.target_user_id).first()
            if target else None
        )
        result.append({
            "id": m.id,
            "target_user_id": m.target_user_id,
            "target_user_name": (target.name or target.username) if target else "",
            "target_user_avatar": (target.avatar or "") if target else "",
            "target_user_school": (target.school or "") if target else "",
            "target_card_interests": _decode(target_card.interest_tags, []) if target_card else [],
            "target_card_intent": _decode(target_card.social_intent, []) if target_card else [],
            "my_score": m.match_score or 0,
            "their_score": m.their_score or 0,
            "my_reasons": _decode(m.match_reasons, []),
            "their_reasons": _decode(m.their_reasons, []),
            "intent_type": m.intent_type or "buddy",
            "suggested_opening": m.suggested_opening or "",
            "status": m.status or "new",
            "peer_match_id": m.peer_match_id,
            "created_at": m.created_at,
        })
    return result


# ==================== Phase 8B: 继续聊 ====================

# 交互状态不允许继续聊的 outcome 集合
_ATOA_TERMINAL_OUTCOMES = {"blocked", "connected", "incompatible"}


async def continue_atoa_conversation(
    db: Session,
    user_id: str,
    interaction_id: str,
) -> dict:
    """
    Phase 8B：用户选择「继续聊」，触发分身续聊 ≤3 轮并追加到现有对话。
    只有 user_a（发起方）可以操作。
    """
    interaction = db.query(AvatarAtoaInteraction).filter(
        AvatarAtoaInteraction.id == interaction_id
    ).first()
    if not interaction:
        raise ApiException(code=NOT_FOUND, message="AtoA 互动记录不存在", status_code=404)
    if interaction.user_a_id != user_id:
        raise ApiException(code=PARAM_INVALID, message="无权操作此互动记录", status_code=403)
    if interaction.outcome in _ATOA_TERMINAL_OUTCOMES:
        raise ApiException(
            code=PARAM_INVALID,
            message=f"当前状态 '{interaction.outcome}' 不允许继续聊",
        )

    card_a = db.query(AvatarCard).filter(AvatarCard.user_id == interaction.user_a_id).first()
    card_b = db.query(AvatarCard).filter(AvatarCard.user_id == interaction.user_b_id).first()
    if not card_a or not card_b:
        raise ApiException(code=NOT_FOUND, message="分身名片不完整，无法续聊", status_code=400)

    prior_conversation = _decode(interaction.conversation, [])
    new_turns = await _simulate_atoa_conversation(
        card_a, card_b,
        max_rounds=3,
        prior_conversation=prior_conversation,
    )

    # 追加对话
    all_conversation = prior_conversation + new_turns
    interaction.conversation = _encode(all_conversation)
    interaction.interaction_phase = (interaction.interaction_phase or 1) + 1
    interaction.user_decision = "continue"
    # outcome 回到 pending_user_decision（等待用户下一步决策）
    if interaction.outcome not in ("mutual",):
        interaction.outcome = "pending_user_decision"
    interaction.updated_at = _now_ms()
    db.commit()

    other = db.query(User).filter(User.id == interaction.user_b_id).first()
    return {
        "id": interaction.id,
        "user_b_id": interaction.user_b_id,
        "user_b_name": (other.name or other.username) if other else "",
        "outcome": interaction.outcome,
        "interaction_phase": interaction.interaction_phase,
        "new_turns": new_turns,
        "conversation": all_conversation,
        "updated_at": interaction.updated_at,
    }


# ==================== Phase 8C: 最终决策 ====================

async def decide_atoa_outcome(
    db: Session,
    user_id: str,
    interaction_id: str,
    decision: str,
    opening_message: Optional[str] = None,
) -> dict:
    """
    Phase 8C：用户对 AtoA 互动做最终决策。
    decision = "block"   → 禁止往下聊：outcome=blocked，关联 match dismissed
    decision = "connect" → 结交搭子：发起 social match，outcome=connected
    """
    if decision not in ("block", "connect"):
        raise ApiException(code=PARAM_INVALID, message="decision 只能是 block 或 connect")

    interaction = db.query(AvatarAtoaInteraction).filter(
        AvatarAtoaInteraction.id == interaction_id
    ).first()
    if not interaction:
        raise ApiException(code=NOT_FOUND, message="AtoA 互动记录不存在", status_code=404)
    if interaction.user_a_id != user_id:
        raise ApiException(code=PARAM_INVALID, message="无权操作此互动记录", status_code=403)
    if interaction.outcome in ("blocked", "connected"):
        raise ApiException(
            code=PARAM_INVALID,
            message=f"该互动已经是终态 '{interaction.outcome}'，不可重复决策",
        )

    now = _now_ms()

    if decision == "block":
        interaction.outcome = "blocked"
        interaction.user_decision = "block"
        interaction.is_visible_to_b = False
        interaction.updated_at = now

        # 同步关联的 AtoA AvatarMatch → dismissed
        match = db.query(AvatarMatch).filter(
            AvatarMatch.user_id == user_id,
            AvatarMatch.target_user_id == interaction.user_b_id,
            AvatarMatch.match_type == "atoa",
            AvatarMatch.status != "dismissed",
        ).first()
        if match:
            match.status = "dismissed"
            _sync_atoa_mutual_flag(db, match.id, False)

        db.commit()
        return {"outcome": "blocked", "social_match_id": None}

    # decision == "connect"
    # 找关联的 AtoA AvatarMatch（mutual）
    match = db.query(AvatarMatch).filter(
        AvatarMatch.user_id == user_id,
        AvatarMatch.target_user_id == interaction.user_b_id,
        AvatarMatch.match_type == "atoa",
        AvatarMatch.status != "dismissed",
    ).first()

    if not match:
        # 若对方还没互通（one_sided），仍允许主动发起搭子申请
        post_b = (
            db.query(PlazaPost)
            .filter(PlazaPost.user_id == interaction.user_b_id)
            .order_by(PlazaPost.created_at.desc())
            .first()
        )
        if not post_b:
            raise ApiException(
                code=NOT_FOUND,
                message="对方暂无帖子，无法发起搭子申请，可先继续聊",
                status_code=400,
            )
        match_id_temp = str(uuid4())
        match = AvatarMatch(
            id=match_id_temp,
            user_id=user_id,
            post_id=post_b.id,
            target_user_id=interaction.user_b_id,
            match_score=interaction.score_a or 0,
            their_score=interaction.score_b or 0,
            match_reasons=interaction.reasons_a or "[]",
            their_reasons=interaction.reasons_b or "[]",
            agent_conversation=interaction.conversation or "[]",
            status="new",
            match_type="atoa",
            intent_type="buddy",
            created_at=now,
        )
        db.add(match)
        db.flush()

    result = start_chat_from_match(db, user_id, match.id, opening_message)
    social_match_id = result.get("social_match_id") or ""

    interaction.outcome = "connected"
    interaction.user_decision = "connect"
    interaction.is_visible_to_b = True
    # 存 social.Match.id，便于 §6.9 respond 后同步 connect_confirmed / connect_rejected
    interaction.triggered_match_id = social_match_id or None
    interaction.updated_at = now
    db.commit()

    return {"outcome": "connected", "social_match_id": social_match_id}
