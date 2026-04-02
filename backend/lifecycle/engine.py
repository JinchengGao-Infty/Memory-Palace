"""
Lifecycle Engine — Phases 1-3

Phase 1: Clean expired working-layer memories
Phase 2: Promote working → core based on score or fast-track rules
Phase 3: Core deduplication via vector similarity (requires sqlite-vec)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select, update, and_, text

from db.sqlite_client import SQLiteClient, Memory
from db.models_lifecycle import LifecycleLog

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


PROMOTE_THRESHOLD = _env_float("LIFECYCLE_PROMOTE_THRESHOLD", 0.4)
DEDUP_SIMILARITY_THRESHOLD = _env_float("LIFECYCLE_DEDUP_SIMILARITY_THRESHOLD", 0.92)

# Categories eligible for fast-track promotion
_FAST_TRACK_CATEGORIES = frozenset({"identity", "constraint"})


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LifecycleEngine:
    """Automated lifecycle maintenance for memories."""

    def __init__(self, client: SQLiteClient) -> None:
        self._client = client

    async def run(self) -> Dict[str, Any]:
        """Run all phases sequentially, return audit summary."""
        results: Dict[str, Any] = {}
        results["phase1"] = await self._phase1_clean_expired()
        results["phase2"] = await self._phase2_promote()
        results["phase3"] = await self._phase3_dedup()
        return results

    # ------------------------------------------------------------------
    # Phase 1: Clean expired working
    # ------------------------------------------------------------------

    async def _phase1_clean_expired(self) -> Dict[str, Any]:
        now = _utc_now_naive()
        async with self._client.session() as session:
            # Find expired working memories
            stmt = select(Memory).where(
                and_(
                    Memory.layer == "working",
                    Memory.expires_at < now,
                    Memory.deprecated == False,  # noqa: E712
                )
            )
            result = await session.execute(stmt)
            expired = result.scalars().all()

            deleted_ids: List[int] = []
            for mem in expired:
                mem.deprecated = True
                deleted_ids.append(mem.id)

            details = {"deleted_count": len(deleted_ids), "deleted_ids": deleted_ids}

        await self._log_phase("phase1_clean_expired", details)
        logger.info("Phase 1: deprecated %d expired working memories", len(deleted_ids))
        return details

    # ------------------------------------------------------------------
    # Phase 2: Promote working → core
    # ------------------------------------------------------------------

    async def _phase2_promote(self) -> Dict[str, Any]:
        now = _utc_now_naive()
        promoted_ids: List[int] = []
        skipped_ids: List[int] = []

        async with self._client.session() as session:
            stmt = select(Memory).where(
                and_(
                    Memory.layer == "working",
                    Memory.expires_at >= now,
                    Memory.deprecated == False,  # noqa: E712
                )
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()

            for mem in candidates:
                # Fast track: identity/constraint with sufficient confidence
                if (
                    mem.category in _FAST_TRACK_CATEGORIES
                    and mem.confidence >= 0.3
                ):
                    mem.layer = "core"
                    mem.expires_at = None
                    promoted_ids.append(mem.id)
                    continue

                # Score-based promotion
                access_factor = min((mem.access_count or 0) / 5.0, 1.0)
                vitality_factor = mem.vitality_score or 0.0
                importance = mem.importance or 0.0
                score = importance * 0.3 + access_factor * 0.4 + vitality_factor * 0.3

                if score >= PROMOTE_THRESHOLD:
                    mem.layer = "core"
                    mem.expires_at = None
                    promoted_ids.append(mem.id)
                else:
                    skipped_ids.append(mem.id)

        details = {
            "promoted_count": len(promoted_ids),
            "skipped_count": len(skipped_ids),
            "promoted_ids": promoted_ids,
            "skipped_ids": skipped_ids,
        }
        await self._log_phase("phase2_promote", details)
        logger.info(
            "Phase 2: promoted %d, skipped %d working memories",
            len(promoted_ids),
            len(skipped_ids),
        )
        return details

    # ------------------------------------------------------------------
    # Phase 3: Core deduplication
    # ------------------------------------------------------------------

    async def _phase3_dedup(self) -> Dict[str, Any]:
        # Check if sqlite-vec is available
        if not self._client._sqlite_vec_knn_ready:
            details: Dict[str, Any] = {"skipped": "sqlite_vec_unavailable"}
            await self._log_phase("phase3_dedup", details)
            logger.info("Phase 3: skipped — sqlite-vec unavailable")
            return details

        merged_pairs: List[Dict[str, int]] = []

        async with self._client.session() as session:
            # Get all non-deprecated core memories that have chunks indexed
            core_stmt = select(Memory).where(
                and_(
                    Memory.layer == "core",
                    Memory.deprecated == False,  # noqa: E712
                )
            ).order_by(Memory.id)
            result = await session.execute(core_stmt)
            core_memories = result.scalars().all()

            if len(core_memories) < 2:
                details = {"merged_count": 0, "skipped": "too_few_memories"}
                await self._log_phase("phase3_dedup", details)
                return details

            # Build a map of memory_id → memory for quick lookup
            mem_map = {m.id: m for m in core_memories}

            # For each pair, compare via vector similarity using chunk embeddings
            # We use the vec0 table directly for pairwise comparison
            knn_table = self._client._sqlite_vec_knn_table

            # Get all chunk embeddings for core memories
            chunk_query = text(
                "SELECT mc.memory_id, mc.id AS chunk_id "
                "FROM memory_chunks mc "
                "JOIN memories m ON m.id = mc.memory_id "
                "WHERE m.layer = 'core' AND m.deprecated = 0 "
                "ORDER BY mc.memory_id, mc.chunk_index"
            )
            chunk_result = await session.execute(chunk_query)
            chunk_rows = chunk_result.fetchall()

            # Group chunks by memory_id
            memory_chunks: Dict[int, List[int]] = {}
            for row in chunk_rows:
                mid = row[0]
                cid = row[1]
                if mid not in memory_chunks:
                    memory_chunks[mid] = []
                memory_chunks[mid].append(cid)

            # For memories with chunks, compare first chunk of each pair
            memory_ids_with_chunks = [
                mid for mid in mem_map if mid in memory_chunks
            ]

            deprecated_ids = set()
            for i, mid_a in enumerate(memory_ids_with_chunks):
                if mid_a in deprecated_ids:
                    continue
                chunk_a = memory_chunks[mid_a][0]  # first chunk

                for mid_b in memory_ids_with_chunks[i + 1:]:
                    if mid_b in deprecated_ids:
                        continue
                    chunk_b = memory_chunks[mid_b][0]

                    # Use sqlite-vec to compute similarity between two chunks
                    sim_query = text(
                        f"SELECT 1.0 - vec_distance_cosine("
                        f"  (SELECT vector FROM {knn_table} WHERE rowid = :chunk_a),"
                        f"  (SELECT vector FROM {knn_table} WHERE rowid = :chunk_b)"
                        f") AS similarity"
                    )
                    try:
                        sim_result = await session.execute(
                            sim_query, {"chunk_a": chunk_a, "chunk_b": chunk_b}
                        )
                        row = sim_result.fetchone()
                        if row is None or row[0] is None:
                            continue
                        similarity = float(row[0])
                    except Exception:
                        logger.debug(
                            "Failed to compute similarity for chunks %d/%d",
                            chunk_a,
                            chunk_b,
                            exc_info=True,
                        )
                        continue

                    if similarity >= DEDUP_SIMILARITY_THRESHOLD:
                        # Keep the one with higher importance
                        mem_a = mem_map[mid_a]
                        mem_b = mem_map[mid_b]
                        keep, discard = (
                            (mem_a, mem_b)
                            if (mem_a.importance or 0) >= (mem_b.importance or 0)
                            else (mem_b, mem_a)
                        )
                        discard.deprecated = True
                        discard.migrated_to = keep.id
                        deprecated_ids.add(discard.id)
                        merged_pairs.append(
                            {"kept": keep.id, "discarded": discard.id, "similarity": round(similarity, 4)}
                        )

        details = {
            "merged_count": len(merged_pairs),
            "merged_pairs": merged_pairs,
        }
        await self._log_phase("phase3_dedup", details)
        logger.info("Phase 3: merged %d duplicate pairs", len(merged_pairs))
        return details

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    async def _log_phase(self, phase: str, details: Dict[str, Any]) -> None:
        """Insert into lifecycle_log table."""
        async with self._client.session() as session:
            log_entry = LifecycleLog(
                phase=phase,
                details=json.dumps(details, default=str),
            )
            session.add(log_entry)
