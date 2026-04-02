"""Tests for Lifecycle Engine — Phases 1-3."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from sqlalchemy import select, text

from db.sqlite_client import Memory, SQLiteClient
from db.models_lifecycle import LifecycleLog


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
        """engine.run() should return results for all three phases."""
        client = SQLiteClient(_sqlite_url(tmp_path / "run.db"))
        await client.init_db()

        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)
        results = await engine.run()

        assert "phase1" in results
        assert "phase2" in results
        assert "phase3" in results
        # Phase 3 should skip (no sqlite-vec in tests)
        assert results["phase3"].get("skipped") == "sqlite_vec_unavailable"

        # Verify lifecycle_log has entries
        async with client.session() as session:
            log_result = await session.execute(
                select(LifecycleLog).order_by(LifecycleLog.id)
            )
            logs = log_result.scalars().all()
            assert len(logs) == 3
            phases = [log.phase for log in logs]
            assert phases == [
                "phase1_clean_expired",
                "phase2_promote",
                "phase3_dedup",
            ]

        await client.close()
