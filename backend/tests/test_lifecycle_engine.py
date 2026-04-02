"""Tests for Lifecycle Engine — Phases 1-6."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from sqlalchemy import func, select, text

from db.sqlite_client import Memory, SQLiteClient
from db.models_lifecycle import LifecycleLog, MemoryFeedback


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _create_working_memory(
    client: SQLiteClient,
    content: str,
    *,
    expires_at: datetime,
    importance: float = 0.5,
    access_count: int = 0,
    vitality_score: float = 1.0,
    category: str | None = None,
    confidence: float = 1.0,
) -> int:
    """Helper: create a memory and set it to working layer with given fields."""
    created = await client.create_memory(
        parent_path="",
        content=content,
        priority=0,
        title=None,
        domain="core",
    )
    mem_id = created["id"]
    async with client.session() as session:
        mem = await session.get(Memory, mem_id)
        mem.layer = "working"
        mem.expires_at = expires_at
        mem.importance = importance
        mem.access_count = access_count
        mem.vitality_score = vitality_score
        mem.category = category
        mem.confidence = confidence
    return mem_id


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------


class TestPhase1CleanExpired:
    @pytest.mark.asyncio
    async def test_phase1_cleans_expired_working(self, tmp_path: Path) -> None:
        """Working memory with past expires_at should be deprecated after phase1."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p1a.db"))
        await client.init_db()

        past = _utc_now_naive() - timedelta(hours=1)
        mem_id = await _create_working_memory(client, "expired memo", expires_at=past)

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase1_clean_expired()

        assert result["deleted_count"] == 1
        assert mem_id in result["deleted_ids"]

        # Verify in DB
        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.deprecated is True

        await client.close()

    @pytest.mark.asyncio
    async def test_phase1_keeps_unexpired_working(self, tmp_path: Path) -> None:
        """Working memory with future expires_at should survive phase1."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p1b.db"))
        await client.init_db()

        future = _utc_now_naive() + timedelta(hours=24)
        mem_id = await _create_working_memory(client, "still valid", expires_at=future)

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase1_clean_expired()

        assert result["deleted_count"] == 0

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.deprecated is False
            assert mem.layer == "working"

        await client.close()


# ---------------------------------------------------------------------------
# Phase 2
# ---------------------------------------------------------------------------


class TestPhase2Promote:
    @pytest.mark.asyncio
    async def test_phase2_promotes_high_score(self, tmp_path: Path) -> None:
        """Working memory with importance=0.8, access_count=5 should promote to core."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p2a.db"))
        await client.init_db()

        future = _utc_now_naive() + timedelta(hours=24)
        mem_id = await _create_working_memory(
            client,
            "important memo",
            expires_at=future,
            importance=0.8,
            access_count=5,
            vitality_score=1.0,
        )
        # Score = 0.8*0.3 + 1.0*0.4 + 1.0*0.3 = 0.24 + 0.4 + 0.3 = 0.94

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase2_promote()

        assert result["promoted_count"] == 1
        assert mem_id in result["promoted_ids"]

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.layer == "core"
            assert mem.expires_at is None

        await client.close()

    @pytest.mark.asyncio
    async def test_phase2_fast_track_identity(self, tmp_path: Path) -> None:
        """category='identity' with confidence >= 0.3 should promote immediately."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p2b.db"))
        await client.init_db()

        future = _utc_now_naive() + timedelta(hours=24)
        mem_id = await _create_working_memory(
            client,
            "I am a test user",
            expires_at=future,
            importance=0.1,  # low importance
            access_count=0,  # no accesses
            vitality_score=0.1,  # low vitality
            category="identity",
            confidence=0.5,
        )
        # Score would be 0.1*0.3 + 0*0.4 + 0.1*0.3 = 0.06 (below threshold)
        # But fast-track should promote it

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase2_promote()

        assert result["promoted_count"] == 1
        assert mem_id in result["promoted_ids"]

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.layer == "core"

        await client.close()

    @pytest.mark.asyncio
    async def test_phase2_skips_low_score(self, tmp_path: Path) -> None:
        """importance=0.1, access_count=0 should stay in working layer."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p2c.db"))
        await client.init_db()

        future = _utc_now_naive() + timedelta(hours=24)
        mem_id = await _create_working_memory(
            client,
            "low priority memo",
            expires_at=future,
            importance=0.1,
            access_count=0,
            vitality_score=0.1,
        )
        # Score = 0.1*0.3 + 0.0*0.4 + 0.1*0.3 = 0.06

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase2_promote()

        assert result["promoted_count"] == 0
        assert result["skipped_count"] == 1
        assert mem_id in result["skipped_ids"]

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.layer == "working"

        await client.close()


# ---------------------------------------------------------------------------
# Phase 3
# ---------------------------------------------------------------------------


class TestPhase3Dedup:
    @pytest.mark.asyncio
    async def test_phase3_skips_when_no_vec(self, tmp_path: Path) -> None:
        """When sqlite-vec is unavailable, phase3 should return skipped."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p3a.db"))
        await client.init_db()

        # sqlite-vec is not loaded in test environments by default
        assert not client._sqlite_vec_knn_ready

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase3_dedup()

        assert result["skipped"] == "sqlite_vec_unavailable"

        await client.close()

    @pytest.mark.asyncio
    async def test_phase3_dedup_merges_similar(self, tmp_path: Path) -> None:
        """Mock vector similarity to test merge logic."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p3b.db"))
        await client.init_db()

        # Create two core memories
        c1 = await client.create_memory(
            parent_path="", content="Memory about cats", priority=0, domain="core"
        )
        c2 = await client.create_memory(
            parent_path="", content="Memory about cats too", priority=0, domain="core"
        )

        # Set different importance so merge picks the higher one
        async with client.session() as session:
            m1 = await session.get(Memory, c1["id"])
            m1.importance = 0.9
            m2 = await session.get(Memory, c2["id"])
            m2.importance = 0.3

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)

        # Directly set the instance attribute to pretend sqlite-vec is ready
        original_vec_ready = client._sqlite_vec_knn_ready
        client._sqlite_vec_knn_ready = True

        try:
            original_session = client.session

            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _mock_session():
                async with original_session() as session:
                    original_execute = session.execute

                    async def _patched_execute(stmt, params=None, **kw):
                        stmt_str = str(stmt) if not isinstance(stmt, str) else stmt
                        if "memory_chunks" in stmt_str and "vec_distance_cosine" not in stmt_str:
                            from unittest.mock import MagicMock

                            mock_result = MagicMock()
                            mock_result.fetchall.return_value = [
                                (c1["id"], 100),
                                (c2["id"], 200),
                            ]
                            return mock_result
                        if "vec_distance_cosine" in stmt_str:
                            from unittest.mock import MagicMock

                            mock_result = MagicMock()
                            mock_result.fetchone.return_value = (0.95,)
                            return mock_result
                        return await original_execute(stmt, params, **kw)

                    session.execute = _patched_execute
                    yield session

            with patch.object(client, "session", _mock_session):
                result = await engine._phase3_dedup()
        finally:
            client._sqlite_vec_knn_ready = original_vec_ready

        assert result["merged_count"] == 1
        pair = result["merged_pairs"][0]
        assert pair["kept"] == c1["id"]  # higher importance
        assert pair["discarded"] == c2["id"]
        assert pair["similarity"] == 0.95

        await client.close()


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------


class TestLifecycleRun:
    @pytest.mark.asyncio
    async def test_full_run_returns_all_phases(self, tmp_path: Path) -> None:
        """engine.run() should return results for all six phases."""
        client = SQLiteClient(_sqlite_url(tmp_path / "run.db"))
        await client.init_db()

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        results = await engine.run()

        for key in ("phase1", "phase2", "phase3", "phase4", "phase5", "phase6"):
            assert key in results
        # Phase 3 should skip (no sqlite-vec in tests)
        assert results["phase3"].get("skipped") == "sqlite_vec_unavailable"

        # Verify lifecycle_log has entries for all 6 phases
        async with client.session() as session:
            log_result = await session.execute(
                select(LifecycleLog).order_by(LifecycleLog.id)
            )
            logs = log_result.scalars().all()
            assert len(logs) == 6
            phases = [log.phase for log in logs]
            assert phases == [
                "phase1_clean_expired",
                "phase2_promote",
                "phase3_dedup",
                "phase4_archive",
                "phase5_compress",
                "phase6_feedback_adjust",
            ]

        await client.close()


# ---------------------------------------------------------------------------
# Helpers for Phase 4-6
# ---------------------------------------------------------------------------


async def _create_core_memory(
    client: SQLiteClient,
    content: str,
    *,
    vitality_score: float = 1.0,
    last_accessed_at: datetime | None = None,
    importance: float = 0.5,
    category: str | None = None,
    source: str = "manual",
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> int:
    """Helper: create a core-layer memory with given fields."""
    created = await client.create_memory(
        parent_path="",
        content=content,
        priority=0,
        title=None,
        domain="core",
    )
    mem_id = created["id"]
    async with client.session() as session:
        mem = await session.get(Memory, mem_id)
        mem.layer = "core"
        mem.vitality_score = vitality_score
        mem.last_accessed_at = last_accessed_at
        mem.importance = importance
        mem.category = category
        mem.source = source
        mem.expires_at = expires_at
        if created_at is not None:
            mem.created_at = created_at
    return mem_id


async def _create_archive_memory(
    client: SQLiteClient,
    content: str,
    *,
    expires_at: datetime,
    category: str | None = None,
    importance: float = 0.5,
) -> int:
    """Helper: create an archive-layer memory."""
    created = await client.create_memory(
        parent_path="",
        content=content,
        priority=0,
        title=None,
        domain="core",
    )
    mem_id = created["id"]
    async with client.session() as session:
        mem = await session.get(Memory, mem_id)
        mem.layer = "archive"
        mem.expires_at = expires_at
        mem.category = category
        mem.importance = importance
    return mem_id


# ---------------------------------------------------------------------------
# Phase 4
# ---------------------------------------------------------------------------


class TestPhase4Archive:
    @pytest.mark.asyncio
    async def test_phase4_archives_stale_core(self, tmp_path: Path) -> None:
        """Core memory with low vitality and stale access should be archived."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p4a.db"))
        await client.init_db()

        stale_date = _utc_now_naive() - timedelta(days=100)
        mem_id = await _create_core_memory(
            client,
            "stale core memory",
            vitality_score=0.1,
            last_accessed_at=stale_date,
        )

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase4_archive()

        assert result["archived_count"] == 1
        assert mem_id in result["archived_ids"]

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.layer == "archive"
            assert mem.expires_at is not None

        await client.close()

    @pytest.mark.asyncio
    async def test_phase4_keeps_healthy_core(self, tmp_path: Path) -> None:
        """Core memory with high vitality and recent access should stay core."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p4b.db"))
        await client.init_db()

        recent = _utc_now_naive() - timedelta(days=1)
        mem_id = await _create_core_memory(
            client,
            "healthy core memory",
            vitality_score=0.8,
            last_accessed_at=recent,
        )

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase4_archive()

        assert result["archived_count"] == 0

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.layer == "core"

        await client.close()

    @pytest.mark.asyncio
    async def test_phase4_uses_created_at_fallback(self, tmp_path: Path) -> None:
        """Core memory with NULL last_accessed_at uses created_at as fallback."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p4c.db"))
        await client.init_db()

        old_created = _utc_now_naive() - timedelta(days=100)
        mem_id = await _create_core_memory(
            client,
            "never accessed memory",
            vitality_score=0.1,
            last_accessed_at=None,
            created_at=old_created,
        )

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase4_archive()

        assert result["archived_count"] == 1
        assert mem_id in result["archived_ids"]

        await client.close()


# ---------------------------------------------------------------------------
# Phase 5
# ---------------------------------------------------------------------------


class TestPhase5Compress:
    @pytest.mark.asyncio
    async def test_phase5_compresses_expired_archive(self, tmp_path: Path) -> None:
        """Expired archive memories should be compressed into a core summary."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p5a.db"))
        await client.init_db()

        past = _utc_now_naive() - timedelta(hours=1)
        mid1 = await _create_archive_memory(
            client, "fact A about topic", expires_at=past, category="preference"
        )
        mid2 = await _create_archive_memory(
            client, "fact B about topic", expires_at=past, category="preference"
        )

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)

        # Mock the LLM call
        with patch(
            "lifecycle.engine._call_compress_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.return_value = "Compressed summary of preference facts"
            result = await engine._phase5_compress()

        assert result["compressed_groups"] == 1
        assert result["originals_deprecated"] == 2

        # Originals should be deprecated
        async with client.session() as session:
            m1 = await session.get(Memory, mid1)
            m2 = await session.get(Memory, mid2)
            assert m1.deprecated is True
            assert m2.deprecated is True

            # New compressed memory should exist
            new_id = m1.migrated_to
            assert new_id is not None
            new_mem = await session.get(Memory, new_id)
            assert new_mem.layer == "core"
            assert new_mem.source == "compressed"
            assert new_mem.importance == 0.3
            assert new_mem.category == "preference"

        await client.close()

    @pytest.mark.asyncio
    async def test_phase5_skips_when_llm_unavailable(self, tmp_path: Path) -> None:
        """When LLM times out, archives should be retained without crash."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p5b.db"))
        await client.init_db()

        past = _utc_now_naive() - timedelta(hours=1)
        mid = await _create_archive_memory(
            client, "some fact", expires_at=past, category="preference"
        )

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)

        with patch(
            "lifecycle.engine._call_compress_llm", new_callable=AsyncMock
        ) as mock_llm:
            mock_llm.side_effect = TimeoutError("LLM unavailable")
            result = await engine._phase5_compress()

        assert result["compressed_groups"] == 0
        assert result.get("errors", 0) >= 1

        # Original should NOT be deprecated
        async with client.session() as session:
            mem = await session.get(Memory, mid)
            assert mem.deprecated is False
            assert mem.layer == "archive"

        await client.close()


# ---------------------------------------------------------------------------
# Phase 6
# ---------------------------------------------------------------------------


class TestPhase6FeedbackAdjust:
    @pytest.mark.asyncio
    async def test_phase6_adjusts_importance_up(self, tmp_path: Path) -> None:
        """Memory with 3 helpful feedbacks should increase importance by 0.1."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p6a.db"))
        await client.init_db()

        mem_id = await _create_core_memory(
            client, "helpful memory", importance=0.5
        )

        # Insert 3 helpful feedbacks
        async with client.session() as session:
            for _ in range(3):
                session.add(MemoryFeedback(memory_id=mem_id, signal="helpful"))

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase6_feedback_adjust()

        assert result["adjusted_count"] >= 1

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert abs(mem.importance - 0.6) < 1e-6
            # Feedback rows should be deleted after processing
            fb_count = await session.scalar(
                select(func.count()).select_from(MemoryFeedback).where(
                    MemoryFeedback.memory_id == mem_id
                )
            )
            assert fb_count == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_phase6_adjusts_importance_down(self, tmp_path: Path) -> None:
        """Memory with 3 wrong feedbacks should decrease importance by 0.15."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p6b.db"))
        await client.init_db()

        mem_id = await _create_core_memory(
            client, "wrong memory", importance=0.5
        )

        async with client.session() as session:
            for _ in range(3):
                session.add(MemoryFeedback(memory_id=mem_id, signal="wrong"))

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase6_feedback_adjust()

        assert result["adjusted_count"] >= 1

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert abs(mem.importance - 0.35) < 1e-6
            # Feedback rows should be deleted after processing
            fb_count = await session.scalar(
                select(func.count()).select_from(MemoryFeedback).where(
                    MemoryFeedback.memory_id == mem_id
                )
            )
            assert fb_count == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_phase6_caps_importance(self, tmp_path: Path) -> None:
        """Memory with importance=1.0 + 3 helpful feedbacks should stay 1.0."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p6c.db"))
        await client.init_db()

        mem_id = await _create_core_memory(
            client, "max importance", importance=1.0
        )

        async with client.session() as session:
            for _ in range(3):
                session.add(MemoryFeedback(memory_id=mem_id, signal="helpful"))

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase6_feedback_adjust()

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.importance == 1.0

        await client.close()

    @pytest.mark.asyncio
    async def test_phase6_feedback_not_reconsumed(self, tmp_path: Path) -> None:
        """Running phase6 twice should not re-apply the same feedback."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p6e.db"))
        await client.init_db()

        mem_id = await _create_core_memory(
            client, "stable memory", importance=0.5
        )

        async with client.session() as session:
            for _ in range(3):
                session.add(MemoryFeedback(memory_id=mem_id, signal="helpful"))

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)

        # First run: importance 0.5 → 0.6
        result1 = await engine._phase6_feedback_adjust()
        assert result1["adjusted_count"] == 1

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert abs(mem.importance - 0.6) < 1e-6

        # Second run: no feedback left, importance stays 0.6
        result2 = await engine._phase6_feedback_adjust()
        assert result2["adjusted_count"] == 0

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert abs(mem.importance - 0.6) < 1e-6

        await client.close()

    @pytest.mark.asyncio
    async def test_phase6_floors_importance(self, tmp_path: Path) -> None:
        """Memory with importance=0.05 + wrong feedbacks should floor at 0.0."""
        client = SQLiteClient(_sqlite_url(tmp_path / "p6d.db"))
        await client.init_db()

        mem_id = await _create_core_memory(
            client, "almost zero importance", importance=0.05
        )

        async with client.session() as session:
            for _ in range(3):
                session.add(MemoryFeedback(memory_id=mem_id, signal="wrong"))

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        result = await engine._phase6_feedback_adjust()

        async with client.session() as session:
            mem = await session.get(Memory, mem_id)
            assert mem.importance == 0.0

        await client.close()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class TestLifecycleScheduler:
    @pytest.mark.asyncio
    async def test_scheduler_respects_enabled_flag(self) -> None:
        """With LIFECYCLE_ENABLED=false, scheduler.start() should not create a task."""
        with patch.dict("os.environ", {"LIFECYCLE_ENABLED": "false"}):
            from lifecycle.scheduler import LifecycleScheduler

            scheduler = LifecycleScheduler()
            assert scheduler._enabled is False
            await scheduler.start()
            assert scheduler._task is None
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_full_lifecycle_run_audit_log(self, tmp_path: Path) -> None:
        """Run full lifecycle via scheduler.trigger(), verify lifecycle_log has 6 phases."""
        client = SQLiteClient(_sqlite_url(tmp_path / "sched.db"))
        await client.init_db()

        from lifecycle.scheduler import LifecycleScheduler

        scheduler = LifecycleScheduler()
        scheduler.set_client_factory(lambda: client)

        result = await scheduler.trigger(force=True)

        assert result["status"] == "completed"
        assert "phases" in result
        phases = result["phases"]
        for key in ("phase1", "phase2", "phase3", "phase4", "phase5", "phase6"):
            assert key in phases

        # Verify lifecycle_log has entries for all 6 phases
        async with client.session() as session:
            log_result = await session.execute(
                select(LifecycleLog).order_by(LifecycleLog.id)
            )
            logs = log_result.scalars().all()
            assert len(logs) == 6
            phase_names = [log.phase for log in logs]
            assert phase_names == [
                "phase1_clean_expired",
                "phase2_promote",
                "phase3_dedup",
                "phase4_archive",
                "phase5_compress",
                "phase6_feedback_adjust",
            ]

        await scheduler.stop()
        await client.close()
