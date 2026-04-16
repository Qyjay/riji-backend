"""Evaluate simple memory recall quality with a JSONL dataset.

JSONL format:
{"user_id":"...","query":"夜跑","expected":["document-id-or-keyword"],"scenario":"chat"}
"""
import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.database import SessionLocal  # noqa: E402
from app.memory.retriever import retrieve_memories  # noqa: E402


def _load_cases(path: str) -> list[dict]:
    cases = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _hit_expected(hits: list[dict], expected: list[str]) -> bool:
    haystack = "\n".join(
        [
            hit.get("document_id", "")
            + "\n"
            + hit.get("source_id", "")
            + "\n"
            + hit.get("title", "")
            + "\n"
            + hit.get("content", "")
            for hit in hits
        ]
    )
    return any(item and item in haystack for item in expected)


def evaluate(path: str, top_k: int) -> dict:
    cases = _load_cases(path)
    db = SessionLocal()
    passed = 0
    details = []
    try:
        for case in cases:
            hits = retrieve_memories(
                db,
                user_id=case["user_id"],
                query=case.get("query", ""),
                scenario=case.get("scenario", "chat"),
                top_k=top_k,
                source_types=case.get("source_types"),
            )
            ok = _hit_expected(hits, case.get("expected", []))
            passed += 1 if ok else 0
            details.append({"query": case.get("query", ""), "ok": ok, "hit_count": len(hits)})
    finally:
        db.close()
    total = len(cases)
    return {
        "total": total,
        "passed": passed,
        "recall_at_k": round(passed / total, 4) if total else 0,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate memory recall against a JSONL dataset.")
    parser.add_argument("dataset", help="Path to JSONL evaluation file.")
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()
    result = evaluate(args.dataset, args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
