"""Re-run plaza post section classification over existing posts.

Idempotent: posts already sitting in the classifier's answer are left untouched.

Usage:
    python scripts/reclassify_plaza_posts.py --dry-run
    python scripts/reclassify_plaza_posts.py --dry-run --only-type dating
    python scripts/reclassify_plaza_posts.py --only-agent-posts
    python scripts/reclassify_plaza_posts.py --user-id <user_id> --limit 50
    python scripts/reclassify_plaza_posts.py --keywords-only
"""
import argparse
import asyncio
import json
import os
import sys
from typing import Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.database import SessionLocal  # noqa: E402
from app.models.plaza import PlazaPost  # noqa: E402
from app.plaza.classifier import (  # noqa: E402
    PLAZA_POST_TYPES,
    classify_by_keywords,
    classify_post_type,
)


def _decode_tags(raw: Optional[str]) -> list:
    try:
        value = json.loads(raw) if raw else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


async def _resolve(post: PlazaPost, keywords_only: bool) -> str:
    tags = _decode_tags(post.tags)
    default = "buddy" if post.mission_id else "share"
    if keywords_only:
        return classify_by_keywords(post.content or "", tags, default=default)
    return await classify_post_type(post.content or "", tags, default=default)


async def reclassify(args: argparse.Namespace) -> dict:
    db = SessionLocal()
    changed = 0
    unchanged = 0
    try:
        query = db.query(PlazaPost)
        if args.user_id:
            query = query.filter(PlazaPost.user_id == args.user_id)
        if args.only_type:
            query = query.filter(PlazaPost.type == args.only_type)
        if args.only_agent_posts:
            query = query.filter(PlazaPost.mission_id.isnot(None))
        query = query.order_by(PlazaPost.created_at.desc())
        if args.limit > 0:
            query = query.limit(args.limit)

        for post in query.all():
            resolved = await _resolve(post, args.keywords_only)
            if resolved == post.type:
                unchanged += 1
                continue
            changed += 1
            print(f"  {post.id} {post.type} -> {resolved} | {(post.content or '')[:48]}")
            if not args.dry_run:
                post.type = resolved

        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()
    return {"changed": changed, "unchanged": unchanged}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reclassify plaza post sections.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing.")
    parser.add_argument("--user-id", default=None, help="Only reclassify one user's posts.")
    parser.add_argument("--only-type", choices=sorted(PLAZA_POST_TYPES), default=None, help="Only reclassify posts currently in this section.")
    parser.add_argument("--only-agent-posts", action="store_true", help="Only reclassify mission recruit posts.")
    parser.add_argument("--limit", type=int, default=0, help="Max posts to process. 0 means no limit.")
    parser.add_argument("--keywords-only", action="store_true", help="Skip the LLM and use keyword rules only.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mode = "dry-run" if args.dry_run else "write"
    print(f"Plaza reclassify started ({mode})")
    result = asyncio.run(reclassify(args))
    print(f"Plaza reclassify finished: {result['changed']} would change, {result['unchanged']} already correct"
          if args.dry_run
          else f"Plaza reclassify finished: {result['changed']} updated, {result['unchanged']} already correct")


if __name__ == "__main__":
    main()
