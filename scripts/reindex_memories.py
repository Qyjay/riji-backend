"""Backfill existing user content into the unified memory system.

Usage:
    python scripts/reindex_memories.py
    python scripts/reindex_memories.py --user-id <user_id>
    python scripts/reindex_memories.py --source diary --source chat_session
    python scripts/reindex_memories.py --rebuild-vector-index
"""
import argparse
import os
import sys
from typing import Iterable, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.database import SessionLocal  # noqa: E402
from app.memory.ingestion import (  # noqa: E402
    ingest_chat_session,
    ingest_diary,
    ingest_material,
    ingest_plaza_comment,
    ingest_plaza_post,
    ingest_social_message,
)
from app.models.chat import ChatSession  # noqa: E402
from app.models.diary import Diary  # noqa: E402
from app.models.material import RawMaterial  # noqa: E402
from app.models.memory import MemoryChunk, MemoryDocument  # noqa: E402
from app.models.plaza import PlazaComment, PlazaPost  # noqa: E402
from app.models.social import SocialMessage  # noqa: E402


SOURCE_LOADERS = {
    "diary": (Diary, ingest_diary, Diary.created_at),
    "material": (RawMaterial, ingest_material, RawMaterial.created_at),
    "chat_session": (ChatSession, ingest_chat_session, ChatSession.created_at),
    "plaza_post": (PlazaPost, ingest_plaza_post, PlazaPost.created_at),
    "plaza_comment": (PlazaComment, ingest_plaza_comment, PlazaComment.created_at),
    "social_message": (SocialMessage, ingest_social_message, SocialMessage.timestamp),
}


def _iter_rows(db, model, order_column, user_id: Optional[str], batch_size: int) -> Iterable:
    query = db.query(model)
    if user_id:
        if hasattr(model, "user_id"):
            query = query.filter(model.user_id == user_id)
        elif hasattr(model, "from_uid"):
            query = query.filter(model.from_uid == user_id)
    query = query.order_by(order_column.asc())

    offset = 0
    while True:
        rows = query.offset(offset).limit(batch_size).all()
        if not rows:
            break
        for row in rows:
            yield row
        offset += len(rows)


def reindex_source(
    *,
    source: str,
    user_id: Optional[str],
    batch_size: int,
    dry_run: bool,
    progress_every: int,
    fail_fast: bool,
) -> dict:
    model, ingester, order_column = SOURCE_LOADERS[source]
    db = SessionLocal()
    count = 0
    failures = []
    try:
        for row in _iter_rows(db, model, order_column, user_id, batch_size):
            count += 1
            try:
                if not dry_run:
                    ingester(db, row)
            except Exception as exc:
                failure = {"source": source, "row_id": getattr(row, "id", ""), "error": str(exc)}
                failures.append(failure)
                if fail_fast:
                    raise
            if progress_every > 0 and count % progress_every == 0:
                print(f"  {source}: processed {count} rows")
    finally:
        db.close()
    return {"processed": count, "failed": len(failures), "failures": failures}


def rebuild_vector_index(*, user_id: Optional[str], batch_size: int, progress_every: int) -> dict:
    """Rebuild vector index for existing chunks when MEMORY_VECTOR_ENABLED=true."""
    from app.memory.indexer import index_chunks

    db = SessionLocal()
    processed = 0
    failures = []
    try:
        query = db.query(MemoryDocument).filter(MemoryDocument.is_deleted == False)  # noqa: E712
        if user_id:
            query = query.filter(MemoryDocument.user_id == user_id)
        document_ids = [item.id for item in query.order_by(MemoryDocument.occurred_at.asc()).all()]
        for document_id in document_ids:
            chunks = (
                db.query(MemoryChunk)
                .filter(MemoryChunk.document_id == document_id)
                .order_by(MemoryChunk.chunk_index.asc())
                .all()
            )
            for idx in range(0, len(chunks), batch_size):
                batch = chunks[idx: idx + batch_size]
                if not batch:
                    continue
                try:
                    index_chunks(batch[0].user_id, batch)
                    processed += len(batch)
                except Exception as exc:
                    failures.append({"document_id": document_id, "error": str(exc)})
                if progress_every > 0 and processed % progress_every == 0:
                    print(f"  vector-index: processed {processed} chunks")
    finally:
        db.close()
    return {"processed": processed, "failed": len(failures), "failures": failures}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill existing content into memory_documents/chunks.")
    parser.add_argument("--user-id", default=None, help="Only reindex one user.")
    parser.add_argument(
        "--source",
        action="append",
        choices=sorted(SOURCE_LOADERS.keys()),
        help="Source type to reindex. Can be provided multiple times. Defaults to all sources.",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true", help="Count rows without writing memory records.")
    parser.add_argument("--progress-every", type=int, default=200, help="Print progress every N rows. Set 0 to disable.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop immediately on the first row-level failure.")
    parser.add_argument("--rebuild-vector-index", action="store_true", help="Reindex existing memory chunks into the vector backend.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = args.source or list(SOURCE_LOADERS.keys())
    total = 0
    total_failed = 0
    all_failures = []
    print("Memory reindex started")
    for source in sources:
        result = reindex_source(
            source=source,
            user_id=args.user_id,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            progress_every=args.progress_every,
            fail_fast=args.fail_fast,
        )
        count = result["processed"]
        total += count
        total_failed += result["failed"]
        all_failures.extend(result["failures"])
        suffix = " counted" if args.dry_run else " indexed"
        failed_text = f", {result['failed']} failed" if result["failed"] else ""
        print(f"- {source}: {count}{suffix}{failed_text}")

    if args.rebuild_vector_index and not args.dry_run:
        vector_result = rebuild_vector_index(
            user_id=args.user_id,
            batch_size=args.batch_size,
            progress_every=args.progress_every,
        )
        total_failed += vector_result["failed"]
        all_failures.extend(vector_result["failures"])
        print(f"- vector-index: {vector_result['processed']} chunks indexed, {vector_result['failed']} failed")

    if all_failures:
        print("Failures:")
        for failure in all_failures[:50]:
            print(f"  - {failure}")
        if len(all_failures) > 50:
            print(f"  ... {len(all_failures) - 50} more failures omitted")
    print(f"Memory reindex finished: {total} rows processed, {total_failed} failures")


if __name__ == "__main__":
    main()
