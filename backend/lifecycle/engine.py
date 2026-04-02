"""
Lifecycle Engine — Phases 1-6

Phase 1: Clean expired working-layer memories
Phase 2: Promote working → core based on score or fast-track rules
Phase 3: Core deduplication via vector similarity (requires sqlite-vec)
Phase 4: Decay core → archive (stale, low-vitality core memories)
Phase 5: Compress archive → core summary (LLM-powered)
Phase 6: Feedback adjustment (importance tuning from user signals)
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import delete, func, select, update, and_, case, text

from db.sqlite_client import SQLiteClient, Memory
from db.models_lifecycle import LifecycleLog, MemoryFeedback

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
ARCHIVE_VITALITY_THRESHOLD = _env_float("LIFECYCLE_ARCHIVE_VITALITY_THRESHOLD", 0.2)
ARCHIVE_STALE_DAYS = _env_float("LIFECYCLE_ARCHIVE_STALE_DAYS", 90)
ARCHIVE_RETENTION_DAYS = _env_float("LIFECYCLE_ARCHIVE_RETENTION_DAYS", 90)

# Categories eligible for fast-track promotion
_FAST_TRACK_CATEGORIES = frozenset({"identity", "constraint"})


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _call_compress_llm(
    category: Optional[str], contents: List[str]
) -> Optional[str]:
    """Call LLM to compress multiple memory contents into a single summary.

    Returns the summary text, or raises on failure.
    """
    base_url = os.environ.get("ROUTER_API_BASE", "http://localhost:8080")
    api_key = os.environ.get("ROUTER_API_KEY", "")
    model = os.environ.get("LIFECYCLE_COMPRESS_MODEL", "default")
    timeout_sec = _env_float("LIFECYCLE_COMPRESS_TIMEOUT_SEC", 10)

    system_prompt = (
        "You are a memory compression assistant. "
        "Given a list of memory facts, produce a single concise summary "
        "that preserves the key information. Output only the summary text."
    )
    user_prompt = (
        f"Category: {category or 'general'}\n\n"
        "Memories to compress:\n"
        + "\n".join(f"- {c}" for c in contents)
    )

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("LLM returned no choices")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ValueError("LLM returned empty content")
        return content


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
        results["phase4"] = await self._phase4_archive()
        results["phase5"] = await self._phase5_compress()
        results["phase6"] = await self._phase6_feedback_adjust()
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
    # Phase 4: Decay core → archive
    # ------------------------------------------------------------------

    async def _phase4_archive(self) -> Dict[str, Any]:
        now = _utc_now_naive()
        stale_cutoff = now - timedelta(days=ARCHIVE_STALE_DAYS)
        retention_delta = timedelta(days=ARCHIVE_RETENTION_DAYS)
        archived_ids: List[int] = []

        async with self._client.session() as session:
            stmt = select(Memory).where(
                and_(
                    Memory.layer == "core",
                    Memory.vitality_score < ARCHIVE_VITALITY_THRESHOLD,
                    Memory.deprecated == False,  # noqa: E712
                )
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()

            for mem in candidates:
                # Use last_accessed_at, fallback to created_at
                effective_date = mem.last_accessed_at or mem.created_at
                if effective_date is not None and effective_date < stale_cutoff:
                    mem.layer = "archive"
                    mem.expires_at = now + retention_delta
                    archived_ids.append(mem.id)

        details = {"archived_count": len(archived_ids), "archived_ids": archived_ids}
        await self._log_phase("phase4_archive", details)
        logger.info("Phase 4: archived %d stale core memories", len(archived_ids))
        return details

    # ------------------------------------------------------------------
    # Phase 5: Compress archive → core summary
    # ------------------------------------------------------------------

    async def _phase5_compress(self) -> Dict[str, Any]:
        now = _utc_now_naive()
        compressed_groups = 0
        originals_deprecated = 0
        errors = 0

        async with self._client.session() as session:
            # Find expired, non-deprecated archive memories
            stmt = select(Memory).where(
                and_(
                    Memory.layer == "archive",
                    Memory.expires_at < now,
                    Memory.deprecated == False,  # noqa: E712
                )
            )
            result = await session.execute(stmt)
            expired_archives = result.scalars().all()

            # Group by category
            by_category: Dict[Optional[str], List[Memory]] = defaultdict(list)
            for mem in expired_archives:
                by_category[mem.category].append(mem)

            for category, memories in by_category.items():
                # Build content for LLM
                contents = [m.content for m in memories]
                try:
                    summary = await _call_compress_llm(category, contents)
                except Exception:
                    logger.warning(
                        "Phase 5: LLM failed for category=%s, skipping %d memories",
                        category,
                        len(memories),
                        exc_info=True,
                    )
                    errors += 1
                    continue

                if not summary:
                    errors += 1
                    continue

                # Create compressed memory
                new_mem = Memory(
                    content=summary,
                    layer="core",
                    source="compressed",
                    importance=0.3,
                    category=category,
                    vitality_score=1.0,
                    created_at=now,
                )
                session.add(new_mem)
                await session.flush()  # get new_mem.id

                # Mark originals as deprecated, point to new memory
                for mem in memories:
                    mem.deprecated = True
                    mem.migrated_to = new_mem.id

                compressed_groups += 1
                originals_deprecated += len(memories)

        details = {
            "compressed_groups": compressed_groups,
            "originals_deprecated": originals_deprecated,
            "errors": errors,
        }
        await self._log_phase("phase5_compress", details)
        logger.info(
            "Phase 5: compressed %d groups (%d originals), %d errors",
            compressed_groups,
            originals_deprecated,
            errors,
        )
        return details

    # ------------------------------------------------------------------
    # Phase 6: Feedback adjustment
    # ------------------------------------------------------------------

    async def _phase6_feedback_adjust(self) -> Dict[str, Any]:
        adjusted_ids: List[int] = []
        category_stats: Dict[str, Dict[str, Any]] = {}

        async with self._client.session() as session:
            # Query feedback counts grouped by memory_id and signal
            stmt = (
                select(
                    MemoryFeedback.memory_id,
                    MemoryFeedback.signal,
                    func.count().label("cnt"),
                )
                .group_by(MemoryFeedback.memory_id, MemoryFeedback.signal)
            )
            result = await session.execute(stmt)
            rows = result.all()

            # Aggregate per memory_id
            feedback_map: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for memory_id, signal, cnt in rows:
                feedback_map[memory_id][signal] = cnt

            # Per-category negative tracking
            cat_negative: Dict[str, int] = defaultdict(int)
            cat_total: Dict[str, int] = defaultdict(int)

            for memory_id, signals in feedback_map.items():
                total = sum(signals.values())
                if total < 3:
                    continue

                helpful = signals.get("helpful", 0)
                wrong = signals.get("wrong", 0)
                outdated = signals.get("outdated", 0)
                negative = wrong + outdated

                mem = await session.get(Memory, memory_id)
                if mem is None or mem.deprecated:
                    continue

                # Track per-category stats
                cat_key = mem.category or "_uncategorized"
                cat_negative[cat_key] += negative
                cat_total[cat_key] += total

                adjusted = False
                if helpful / total > 0.7:
                    mem.importance = min(1.0, (mem.importance or 0.0) + 0.1)
                    adjusted = True
                elif negative / total > 0.5:
                    mem.importance = max(0.0, (mem.importance or 0.0) - 0.15)
                    adjusted = True

                if adjusted:
                    adjusted_ids.append(memory_id)

                # Delete consumed feedback rows regardless of adjustment
                await session.execute(
                    delete(MemoryFeedback).where(
                        MemoryFeedback.memory_id == memory_id
                    )
                )

            # Compute category stats for logging
            for cat_key in set(cat_negative) | set(cat_total):
                t = cat_total.get(cat_key, 0)
                n = cat_negative.get(cat_key, 0)
                category_stats[cat_key] = {
                    "total_feedbacks": t,
                    "negative_feedbacks": n,
                    "negative_rate": round(n / t, 4) if t > 0 else 0.0,
                }

        details = {
            "adjusted_count": len(adjusted_ids),
            "adjusted_ids": adjusted_ids,
            "category_stats": category_stats,
        }
        await self._log_phase("phase6_feedback_adjust", details)
        logger.info("Phase 6: adjusted importance for %d memories", len(adjusted_ids))
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
