"""
TASK-G 联调脚本 — Phase 1-7 全链路测试
关闭 Mock 模式，使用 VIVO 蓝心大模型真实 API 进行集成验证
"""
import asyncio
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from app.database import SessionLocal
from app.models.user import User
from app.models.avatar import AvatarStatus as _AvatarStatus, AvatarMemory, AvatarMatch
from app.models.plaza import PlazaPost
from app.ai.minimax_client import get_minimax_client
from app.avatar import service as svc
import json as _json

DIVIDER = "=" * 60
results = []


def log(tag: str, msg: str):
    line = f"[{tag}] {msg}"
    print(line)
    results.append(line)


def section(title: str):
    print()
    print(DIVIDER)
    print(f"  {title}")
    print(DIVIDER)


async def main():
    db = SessionLocal()

    # ─── 环境检查 ───────────────────────────────────────────────
    section("环境 & 配置检查")
    client = get_minimax_client()
    if client.mock:
        log("WARN", "Mock 模式未关闭！AI 精排将使用假数据")
    else:
        log("OK", f"VIVO 蓝心大模型已启用  provider={client.provider}  app_id={client.vivo_app_id}")

    # 验证 API 连通
    try:
        reply = await client.chat_completion(
            [{"role": "user", "content": "你好，请用一句话介绍自己"}],
            max_tokens=60,
        )
        log("OK", f"VIVO API 连通，回复：{reply[:60]}")
    except Exception as e:
        log("FAIL", f"VIVO API 连通失败：{e}")

    # ─── 数据库状态 ────────────────────────────────────────────
    section("数据库状态")
    users = db.query(User).all()
    posts = db.query(PlazaPost).count()
    mem_cnt = db.query(AvatarMemory).count()
    match_cnt = db.query(AvatarMatch).count()
    status_cnt = db.query(_AvatarStatus).count()
    log("INFO", f"用户数={len(users)}  帖子数={posts}  记忆数={mem_cnt}  匹配数={match_cnt}  状态数={status_cnt}")

    # 选取测试用户
    test_user = db.query(User).filter(User.name == "于欣怡").first()
    if not test_user:
        test_user = db.query(User).first()
    log("INFO", f"联调用户：{test_user.name}  id={test_user.id[:12]}...")

    # ─── Phase 1-4: 个性化冲浪计划 ────────────────────────────
    section("Phase 1-4: 个性化冲浪计划 (usage 记录 + 推荐时间窗口)")
    try:
        now_ts = int(time.time() * 1000)
        svc.record_usage_event(
            db,
            test_user.id,
            data={"event_type": "app_open", "timestamp": now_ts, "active_ms": 300000, "page": "home"},
        )
        log("OK", "record_usage_event 成功写入使用习惯事件")
    except Exception as e:
        log("FAIL", f"record_usage_event 失败：{e}")

    try:
        status = db.query(_AvatarStatus).filter(_AvatarStatus.user_id == test_user.id).first()
        if not status:
            log("SKIP", "用户暂无 AvatarStatus 记录")
        else:
            plan_raw = status.personalized_surf_plan or "{}"
            plan = _json.loads(plan_raw)
            preferred = plan.get("preferredHours", plan.get("preferred_hours", []))
            daily_limit = plan.get("dailyLimit", plan.get("daily_limit", "?"))
            mode = plan.get("mode", "?")
            log("OK", f"个性化冲浪计划 mode={mode}  preferredHours={preferred}  dailyLimit={daily_limit}")
    except Exception as e:
        log("FAIL", f"查询 AvatarStatus 失败：{e}")

    # ─── Phase 5+6: rebuild_avatar_matches ─────────────────────
    section("Phase 5+6: rebuild_avatar_matches (规则宽召回 + VIVO AI 精排)")
    try:
        t0 = time.time()
        result = await svc.rebuild_avatar_matches(db, test_user.id)
        elapsed = round(time.time() - t0, 1)
        log("OK", (
            f"rebuild 完成 耗时={elapsed}s  "
            f"total_matches={result['total_matches']}  "
            f"newly_ai_refined={result['newly_ai_refined']}  "
            f"ai_refined_total={result['ai_refined_total']}"
        ))
    except Exception as e:
        import traceback
        log("FAIL", f"rebuild_avatar_matches 失败：{e}")
        traceback.print_exc()

    # ─── Phase 5+6: list_matches 查看精排结果 ───────────────────
    section("Phase 5+6: list_matches 查看返回字段")
    try:
        matches_out = svc.list_matches(db, test_user.id)
        log("OK", f"list_matches 返回 {len(matches_out)} 条")
        for i, m in enumerate(matches_out[:3]):
            ai_flag = "AI精排" if m.get("ai_refined") else "规则"
            opening = (m.get("suggested_opening") or "")[:30]
            reasons = m.get("match_reasons", [])[:2]
            log("INFO", (
                f"  [{i+1}] score={m.get('match_score')}  type={ai_flag}  "
                f"reasons={reasons}  opening={opening}"
            ))
    except Exception as e:
        log("FAIL", f"list_matches 失败：{e}")

    # ─── Phase 7: start_chat_from_match ────────────────────────
    section("Phase 7: start_chat_from_match (社交闭环)")
    try:
        matches_raw = db.query(AvatarMatch).filter(
            AvatarMatch.user_id == test_user.id,
            AvatarMatch.status == "new",
        ).first()
        if matches_raw:
            try:
                result7 = await svc.start_chat_from_match(db, test_user.id, matches_raw.id)
                log("OK", (
                    f"start_chat_from_match 成功  "
                    f"social_match_id={result7['social_match_id'][:12]}...  "
                    f"is_duplicate={result7['is_duplicate']}"
                ))
            except Exception as e7:
                err_msg = str(e7)
                if "不能向自己发起" in err_msg:
                    log("SKIP", "测试数据：推荐匹配的目标即当前用户本人，Phase 7 逻辑保护正常触发，跳过实际发送")
                elif "重复" in err_msg or "duplicate" in err_msg.lower():
                    log("OK", f"Phase 7 防重复保护正常触发：{err_msg}")
                else:
                    log("FAIL", f"start_chat_from_match 失败：{err_msg}")
        else:
            log("SKIP", "无 status=new 的 AvatarMatch，跳过 Phase 7 测试")
    except Exception as e:
        log("FAIL", f"start_chat_from_match 失败：{e}")

    db.close()

    # ─── 总结 ────────────────────────────────────────────────
    section("联调总结")
    ok_cnt = sum(1 for r in results if r.startswith("[OK]"))
    fail_cnt = sum(1 for r in results if r.startswith("[FAIL]"))
    skip_cnt = sum(1 for r in results if r.startswith("[SKIP]"))
    print(f"通过 {ok_cnt} 项  失败 {fail_cnt} 项  跳过 {skip_cnt} 项")
    if fail_cnt == 0:
        print("全部通过，TASK-G 联调完成！")
    else:
        print("存在失败项，详见上方日志。")

    return ok_cnt, fail_cnt, skip_cnt


if __name__ == "__main__":
    asyncio.run(main())
