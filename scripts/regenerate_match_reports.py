"""重新生成存量匹配报告

早期版本的报告生成用的是自然语言 prompt，解析不出结构化分数，分数被回落成兜底的 75。
本脚本对这类报告重新调用大模型生成，把真实分数写回 matches.match_report。

幂等：默认只挑分数等于兜底值的报告；刷新成功后分数不再是兜底值，重复执行不会再选中它。
搭子申请理由（match_report 里的 reason 字段）会原样保留。

用法：
    python scripts/regenerate_match_reports.py --all                    # dry-run，只列出会被刷新的报告
    python scripts/regenerate_match_reports.py --all --apply            # 实际重新生成并落库
    python scripts/regenerate_match_reports.py --match-id <id> --apply  # 只处理指定 match（可重复传）
    python scripts/regenerate_match_reports.py --all --any-score        # 不限分数，所有已有报告都算候选
    python scripts/regenerate_match_reports.py --all --limit 5 --apply
"""
import argparse
import asyncio
import json
import os
import sys
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.database import SessionLocal  # noqa: E402
from app.models.social import Match  # noqa: E402
from app.models.user import User  # noqa: E402
from app.social.service import (  # noqa: E402
    _MATCH_REPORT_FALLBACK_SCORE,
    _normalize_match_report,
    refresh_match_report,
)


def _stored_report(match: Match) -> dict | None:
    """只有落库内容是 JSON 对象才算「已生成过报告」；纯文本是搭子申请理由。"""
    raw = str(match.match_report or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _label(db, match: Match) -> str:
    names = []
    for uid in (match.user_id, match.target_id):
        user = db.query(User).filter(User.id == uid).first()
        names.append((user.username or user.name) if user else uid)
    return " <-> ".join(names)


def _select(db, match_ids: list[str], any_score: bool, limit: int) -> tuple[list, list]:
    query = db.query(Match)
    if match_ids:
        query = query.filter(Match.id.in_(match_ids))
    rows = query.order_by(Match.created_at.desc()).all()

    selected, skipped = [], []
    for match in rows:
        report = _stored_report(match)
        if report is None:
            skipped.append((match, "尚无 JSON 报告（可能只存了搭子申请理由）"))
            continue
        score = _normalize_match_report(report)["compatibility"]
        if not any_score and score != _MATCH_REPORT_FALLBACK_SCORE:
            skipped.append((match, f"分数 {score} 不是兜底值，无需刷新"))
            continue
        selected.append((match, score))

    if match_ids:
        found = {match.id for match, _ in selected} | {match.id for match, _ in skipped}
        for match_id in match_ids:
            if match_id not in found:
                skipped.append((None, f"{match_id} 不存在"))

    if limit > 0:
        selected = selected[:limit]
    return selected, skipped


async def run(match_ids: list[str], apply: bool, any_score: bool, limit: int, sleep: float) -> int:
    db = SessionLocal()
    failures = 0
    try:
        selected, skipped = _select(db, match_ids, any_score, limit)

        print(f"模式: {'实跑（会写库）' if apply else 'dry-run（不写库）'}")
        print(f"候选 {len(selected)} 条 / 跳过 {len(skipped)} 条\n")

        for match, reason in skipped:
            name = f"{match.id} {_label(db, match)}" if match else ""
            print(f"[SKIP] {name} -> {reason}".rstrip())
        if skipped:
            print()

        for index, (match, old_score) in enumerate(selected, start=1):
            head = f"[{index}/{len(selected)}] {match.id} {_label(db, match)} 旧分数={old_score}"
            try:
                report = await refresh_match_report(db, match, persist=apply)
            except Exception as exc:
                failures += 1
                print(f"{head} -> [FAIL] {type(exc).__name__}: {exc}")
                continue
            flag = "已写库" if apply else "dry-run 未写库"
            print(f"{head} -> 新分数={report['compatibility']}（{flag}）")
            print(f"        summary: {report.get('summary', '')}")
            print(f"        analysis: {str(report.get('analysis') or '')[:80]}")
            print(f"        common_points: {report.get('common_points')}")
            dims = report.get("dimensions") or []
            if dims:
                preview = ", ".join(
                    f"{item.get('label')}={item.get('score')}" for item in dims[:4]
                )
                print(f"        dimensions: {preview}")
            if index < len(selected) and sleep > 0:
                time.sleep(sleep)

        print(f"\n完成：成功 {len(selected) - failures} / 失败 {failures}")
        if not apply and selected:
            print("以上均未写库，确认无误后加 --apply 实跑。")
    finally:
        db.close()
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="重新生成存量匹配报告")
    parser.add_argument("--match-id", action="append", default=[], help="指定 match id，可重复传")
    parser.add_argument("--all", action="store_true", help="处理全部已有报告")
    parser.add_argument("--apply", action="store_true", help="实际写库；不传则只做 dry-run")
    parser.add_argument("--any-score", action="store_true", help="不限分数，不只挑兜底分 75 的报告")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条，0 表示不限")
    parser.add_argument("--sleep", type=float, default=1.0, help="两次模型调用之间的间隔秒数")
    args = parser.parse_args()

    match_ids = [x.strip() for x in args.match_id if x.strip()]
    if not match_ids and not args.all:
        parser.error("请指定 --match-id 或 --all")

    return asyncio.run(run(match_ids, args.apply, args.any_score, args.limit, args.sleep))


if __name__ == "__main__":
    sys.exit(main())
