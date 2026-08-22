"""列出或清理小传中的历史占位图片 URL。

默认只 dry-run，不写数据库：
    python scripts/clean_biography_placeholders.py
    python scripts/clean_biography_placeholders.py --apply
"""
import argparse
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.biography.service import is_known_placeholder_media_url  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.biography import BiographyChapter  # noqa: E402


def _decode_illustrations(raw: str) -> list:
    try:
        value = json.loads(raw) if raw else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def clean_placeholders(apply: bool = False) -> dict:
    db = SessionLocal()
    cover_count = 0
    illustration_count = 0
    try:
        for chapter in db.query(BiographyChapter).order_by(BiographyChapter.created_at).all():
            changed = False
            cover_url = str(chapter.cover_image_url or "").strip()
            if is_known_placeholder_media_url(cover_url):
                cover_count += 1
                changed = True
                print(f"chapter={chapter.id} cover_image_url={cover_url}")
                if apply:
                    chapter.cover_image_url = ""

            illustrations = _decode_illustrations(chapter.illustrations)
            kept = []
            for item in illustrations:
                image_url = str(
                    (item or {}).get("image_url") or (item or {}).get("imageUrl") or ""
                ).strip() if isinstance(item, dict) else ""
                if image_url and is_known_placeholder_media_url(image_url):
                    illustration_count += 1
                    changed = True
                    print(f"chapter={chapter.id} illustration_url={image_url}")
                    continue
                kept.append(item)
            if apply and changed:
                chapter.illustrations = json.dumps(kept, ensure_ascii=False)

        if apply:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"covers": cover_count, "illustrations": illustration_count}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List or remove known placeholder URLs from biography chapters."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag the script is always dry-run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mode = "apply" if args.apply else "dry-run"
    print(f"Biography placeholder cleanup started ({mode})")
    result = clean_placeholders(apply=args.apply)
    print(
        "Biography placeholder cleanup finished: "
        f"{result['covers']} covers, {result['illustrations']} illustrations"
    )


if __name__ == "__main__":
    main()
