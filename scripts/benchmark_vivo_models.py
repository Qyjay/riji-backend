"""
蓝心对话模型延迟基准

对比不同模型 / 思维链开关 / reasoning_effort 组合下的首字延迟与总耗时，
用于决定 App 端生产配置。首字延迟直接决定用户在聊天页看到第一个字的等待时间。

用法：
    python scripts/benchmark_vivo_models.py                # 默认矩阵，每档 3 次
    python scripts/benchmark_vivo_models.py --rounds 5     # 每档 5 次
    python scripts/benchmark_vivo_models.py --scenario chat
"""
import argparse
import asyncio
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.minimax_client import MiniMaxClient
from app.config import settings

# 两类真实场景：聊天要的是「马上有反应」，日记生成允许稍慢但不能太久
SCENARIOS = {
    "chat": {
        "system": "你是日记应用 Avalin 的 AI 伙伴，说话简短自然。",
        "user": "今天有点累，不太想学习，怎么办？",
        "max_tokens": 256,
    },
    "diary": {
        "system": "你是日记写作助手，把用户的零散记录整理成一段流畅的日记。",
        "user": "素材：早上八点起床，赶去图书馆抢座位；中午和室友吃了拉面；下午写代码写到六点，"
                "解决了一个困扰两天的 bug，很有成就感；晚上散步看到晚霞很好看。",
        "max_tokens": 800,
    },
}

# (标签, 模型, 开思维链, reasoning_effort)
MATRIX = [
    ("pro + thinking(low)  [当前生产配置]", "Doubao-Seed-2.0-pro", True, "low"),
    ("pro  无thinking(minimal)", "Doubao-Seed-2.0-pro", False, "minimal"),
    ("lite 无thinking(minimal)", "Doubao-Seed-2.0-lite", False, "minimal"),
    ("lite + thinking(low)", "Doubao-Seed-2.0-lite", True, "low"),
    ("mini 无thinking(minimal)", "Doubao-Seed-2.0-mini", False, "minimal"),
]


def build_client(model: str, thinking: bool, effort: str) -> MiniMaxClient:
    """复用 .env 里的凭证，只覆盖被测的模型参数。"""
    return MiniMaxClient(
        api_key="",
        api_base=settings.MINIMAX_API_BASE,
        model=settings.MINIMAX_MODEL,
        mock=False,
        provider="vivo",
        vivo_app_id=settings.VIVO_APP_ID,
        vivo_app_key=settings.VIVO_APP_KEY,
        vivo_api_base=settings.VIVO_API_BASE,
        vivo_model=model,
        vivo_reasoning_effort=effort,
        vivo_enable_thinking=thinking,
        vivo_timeout_sec=settings.VIVO_TIMEOUT_SEC,
    )


async def measure_once(client: MiniMaxClient, scenario: dict) -> tuple[float, float, int, str]:
    """返回 (首字延迟, 总耗时, 字符数, 回复预览)"""
    started = time.time()
    first_at = -1.0
    buffer = ""

    async for chunk in client.stream_chat(
        messages=[{"role": "user", "content": scenario["user"]}],
        system_prompt=scenario["system"],
        max_tokens=scenario["max_tokens"],
    ):
        if first_at < 0:
            first_at = time.time() - started
        buffer += chunk

    total = time.time() - started
    if first_at < 0:
        raise RuntimeError("未收到任何 chunk")

    preview = " ".join(buffer.split())[:50]
    return first_at, total, len(buffer), preview


async def run(scenario_name: str, rounds: int) -> None:
    scenario = SCENARIOS[scenario_name]
    print(f"\n场景: {scenario_name} / 每档 {rounds} 次 / max_tokens={scenario['max_tokens']}")
    print(f"提问: {scenario['user'][:60]}...")

    results: list[dict] = []

    for label, model, thinking, effort in MATRIX:
        print(f"\n{'=' * 70}\n{label}\n  model={model} thinking={thinking} effort={effort}\n{'-' * 70}")
        client = build_client(model, thinking, effort)

        firsts: list[float] = []
        totals: list[float] = []
        lengths: list[int] = []
        error = ""

        for index in range(rounds):
            try:
                first, total, length, preview = await measure_once(client, scenario)
                firsts.append(first)
                totals.append(total)
                lengths.append(length)
                print(f"  #{index + 1} 首字 {first:5.2f}s  总计 {total:6.2f}s  {length:4d} 字  {preview}")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                print(f"  #{index + 1} 失败 -> {error}")
                break

            # 避免连续请求触发限流
            await asyncio.sleep(1.0)

        if firsts:
            results.append({
                "label": label,
                "first": statistics.median(firsts),
                "first_min": min(firsts),
                "first_max": max(firsts),
                "total": statistics.median(totals),
                "length": int(statistics.median(lengths)),
                "samples": len(firsts),
            })
        else:
            results.append({"label": label, "error": error})

    # 汇总表
    print(f"\n{'=' * 82}\n汇总（中位数，按首字延迟升序）\n{'-' * 82}")
    print(f"{'配置':<38} {'首字':>8} {'区间':>14} {'总耗时':>8} {'字数':>6}")
    print("-" * 82)

    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    for item in sorted(ok, key=lambda x: x["first"]):
        span = f"{item['first_min']:.1f}-{item['first_max']:.1f}s"
        print(f"{item['label']:<38} {item['first']:7.2f}s {span:>14} {item['total']:7.2f}s {item['length']:6d}")

    for item in failed:
        print(f"{item['label']:<38} {'失败':>8}  {item['error'][:40]}")

    print("=" * 82)

    if ok:
        best = min(ok, key=lambda x: x["first"])
        baseline = next((r for r in ok if "当前生产配置" in r["label"]), None)
        print(f"\n最快: {best['label']} — 首字 {best['first']:.2f}s")
        if baseline and baseline is not best and baseline["first"] > 0:
            speedup = baseline["first"] / best["first"]
            print(f"相比当前生产配置（首字 {baseline['first']:.2f}s）快 {speedup:.1f} 倍")


def main() -> int:
    parser = argparse.ArgumentParser(description="蓝心对话模型延迟基准")
    parser.add_argument("--rounds", type=int, default=3, help="每个配置重复次数，默认 3")
    parser.add_argument("--scenario", default="chat", choices=sorted(SCENARIOS.keys()),
                        help="测试场景，默认 chat")
    args = parser.parse_args()

    if not str(settings.VIVO_APP_KEY or "").strip():
        print("VIVO_APP_KEY 未配置")
        return 2

    asyncio.run(run(args.scenario, max(1, args.rounds)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
