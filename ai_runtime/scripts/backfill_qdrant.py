"""
Backfill existing document chunks into Qdrant.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Optional

from ai_runtime.core.config import get_config, load_env_file
from ai_runtime.core.database import get_db_manager, init_db_manager
from ai_runtime.core.dependencies import get_container, init_container

logger = logging.getLogger("backfill_qdrant")


async def _initialize():
    load_env_file()
    config = get_config()
    db_manager = init_db_manager(config.database)
    await db_manager.connect()
    container = init_container()
    await container.initialize(config, db_manager)
    return container


async def _shutdown():
    try:
        await get_container().shutdown()
    finally:
        await get_db_manager().disconnect()


async def run_backfill(
    *,
    batch_size: int,
    limit: Optional[int],
    offset: int,
    tenant_id: Optional[str],
    knowledge_base_id: Optional[str],
    reindex_missing: bool,
    dry_run: bool,
) -> int:
    container = await _initialize()
    repository = container.document_repository
    service = container.document_service

    processed = 0
    synced = 0
    skipped_not_indexed = 0
    failed = 0
    current_offset = offset

    try:
        while True:
            if limit is not None and processed >= limit:
                break

            current_batch_size = batch_size
            if limit is not None:
                current_batch_size = min(current_batch_size, limit - processed)
            if current_batch_size <= 0:
                break

            documents = await repository.list_documents_for_vector_backfill(
                limit=current_batch_size,
                offset=current_offset,
                tenant_id=tenant_id,
                knowledge_base_id=knowledge_base_id,
            )
            if not documents:
                break

            for document in documents:
                processed += 1
                try:
                    if not reindex_missing and not document.indexed:
                        skipped_not_indexed += 1
                        logger.warning(
                            "Skip document %s (%s): document is not indexed and --reindex-missing is disabled",
                            document.id,
                            document.title,
                        )
                        continue

                    if dry_run:
                        logger.info(
                            "[dry-run] rebuild Qdrant index for document %s (%s)",
                            document.id,
                            document.title,
                        )
                    else:
                        await service._run_index_document(
                            document=document,
                            target_version=document.index_version,
                        )
                        logger.info(
                            "Rebuilt Qdrant index for document %s (%s)",
                            document.id,
                            document.title,
                        )
                    synced += 1
                except Exception:
                    failed += 1
                    logger.exception(
                        "Failed to backfill document %s (%s)",
                        document.id,
                        document.title,
                    )

            current_offset += len(documents)

    finally:
        await _shutdown()

    logger.info(
        "Backfill finished: processed=%s synced=%s skipped_not_indexed=%s failed=%s",
        processed,
        synced,
        skipped_not_indexed,
        failed,
    )
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill existing documents into Qdrant")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for scanning documents")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of documents to process")
    parser.add_argument("--offset", type=int, default=0, help="Initial document offset")
    parser.add_argument("--tenant-id", type=str, default=None, help="Only backfill one tenant")
    parser.add_argument("--knowledge-base-id", type=str, default=None, help="Only backfill one knowledge base")
    parser.add_argument(
        "--reindex-missing",
        action="store_true",
        help="Regenerate embeddings for documents that do not have vectorized chunks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and print actions without writing to Qdrant",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    return asyncio.run(
        run_backfill(
            batch_size=max(1, args.batch_size),
            limit=args.limit,
            offset=max(0, args.offset),
            tenant_id=args.tenant_id,
            knowledge_base_id=args.knowledge_base_id,
            reindex_missing=bool(args.reindex_missing),
            dry_run=bool(args.dry_run),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
