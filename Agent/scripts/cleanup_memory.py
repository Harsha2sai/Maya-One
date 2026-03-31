#!/usr/bin/env python3
"""
One-time cleanup utility for poisoned/duplicate conversation memories.

Default mode is dry-run. Use --apply to actually delete candidate rows.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any

# Allow running script directly from repo root without manual PYTHONPATH export.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.memory.hybrid_memory_manager import HybridMemoryManager


POISON_PATTERNS = (
    "there's been a misunderstanding",
    "i was referring to someone else",
    "i don't know anything about you",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_conversation(meta: dict[str, Any]) -> bool:
    return str(meta.get("source", "")).lower() == "conversation"


def _iter_all_rows(collection: Any, page_size: int = 500) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    total = int(collection.count())
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    offset = 0
    while offset < total:
        chunk = collection.get(
            offset=offset,
            limit=page_size,
            include=["documents", "metadatas"],
        )
        chunk_ids = list(chunk.get("ids") or [])
        chunk_docs = list(chunk.get("documents") or [])
        chunk_metas = list(chunk.get("metadatas") or [])
        ids.extend(chunk_ids)
        docs.extend(chunk_docs)
        metas.extend(chunk_metas)
        offset += page_size
    return ids, docs, metas


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean poisoned/duplicate conversation memories")
    parser.add_argument("--apply", action="store_true", help="Apply deletions (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility flag; dry-run is already default")
    parser.add_argument(
        "--user-id",
        action="append",
        default=["console_user", "runtime_user"],
        help="Limit cleanup to these user ids (repeatable). Defaults: console_user, runtime_user",
    )
    args = parser.parse_args()

    target_users = {str(u).strip() for u in args.user_id if str(u).strip()}
    manager = HybridMemoryManager()
    collection = manager.retriever.vector_store.collection

    ids, docs, metas = _iter_all_rows(collection)
    total = len(ids)
    print(f"Total items in Chroma: {total}")

    missing_session: set[str] = set()
    poisoned: set[str] = set()
    duplicates: set[str] = set()
    duplicate_groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    for memory_id, doc, raw_meta in zip(ids, docs, metas):
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        user_id = str(meta.get("user_id") or "").strip()
        if target_users and user_id not in target_users:
            continue
        if not _is_conversation(meta):
            continue

        session_id = str(meta.get("session_id") or "").strip()
        normalized_doc = _normalize_text(str(doc or ""))

        if not session_id:
            missing_session.add(memory_id)

        lowered = normalized_doc
        if any(marker in lowered for marker in POISON_PATTERNS):
            poisoned.add(memory_id)

        dedupe_key = (user_id, session_id, normalized_doc)
        duplicate_groups[dedupe_key].append(memory_id)

    for group_ids in duplicate_groups.values():
        if len(group_ids) > 1:
            # Keep the first record, mark the rest for deletion.
            duplicates.update(group_ids[1:])

    candidates = missing_session | poisoned | duplicates

    print(f"Target users: {sorted(target_users)}")
    print(f"Candidates (missing session_id): {len(missing_session)}")
    print(f"Candidates (poison patterns): {len(poisoned)}")
    print(f"Candidates (duplicates): {len(duplicates)}")
    print(f"Total unique candidate deletions: {len(candidates)}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to delete candidates.")
        return 0

    deleted = 0
    failed = 0
    for memory_id in sorted(candidates):
        ok = manager.delete_memory(memory_id)
        if ok:
            deleted += 1
        else:
            failed += 1

    print(f"Deleted: {deleted}")
    print(f"Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
