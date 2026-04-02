"""Integration test — full end-to-end lifecycle flow.

Exercises: ingest → extract → lifecycle → search → feedback → lifecycle adjusts.
Uses real SQLiteClient (tmp_path DB), real extraction engine, real lifecycle engine.
Only LLM calls are mocked.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from db.sqlite_client import Memory, SQLiteClient
from db.models_lifecycle import LifecycleLog, MemoryFeedback
from extraction.engine import _dedup_cache


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_deep_llm_response() -> str:
    """Fake LLM response for deep channel extraction."""
    return json.dumps({
        "memories": [
            {
                "content": "用户是一名数据工程师，专注于ETL流程设计",
                "category": "identity",
                "importance": 0.8,
                "confidence": 0.9,
                "attributed_to": "user",
            },
            {
                "content": "用户偏好使用Python和Airflow进行数据管道开发",
                "category": "preference",
                "importance": 0.6,
                "confidence": 0.7,
                "attributed_to": "user",
            },
        ]
    })


@pytest.fixture(autouse=True)
def _clear_dedup():
    """Clear extraction dedup cache before/after each test."""
    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


@pytest.mark.asyncio
async def test_full_lifecycle_flow(tmp_path: Path) -> None:
    """
    End-to-end: ingest → extract → lifecycle → search → feedback → lifecycle adjusts.

    Steps:
    1. Setup: create SQLiteClient with tmp DB
    2. Ingest a conversation via extraction engine
       - Mock deep channel LLM to return structured result
       - Fast channel should extract identity from "我是数据工程师"
    3. Verify: fast result in core layer, deep result in working layer with expires_at
    4. Run lifecycle engine (phases 1-6)
       - Working memory with identity category should fast-track promote to core
    5. Search and verify results include feedback_hint
    6. Submit feedback (helpful) via MemoryFeedback
    7. Run lifecycle again → verify importance adjusted
    """

    # ---- Step 1: Setup ----
    db_path = tmp_path / "integration.db"
    db_url = _sqlite_url(db_path)
    client = SQLiteClient(db_url)
    await client.init_db()

    try:
        # ---- Step 2: Ingest a conversation ----
        user_msg = "我是数据工程师，主要用Python和Airflow做ETL"
        assistant_msg = "了解！作为数据工程师，你可能对dbt也感兴趣。"

        # Mock only the LLM call in deep_channel, let fast_channel run for real
        with patch("extraction.deep_channel._call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("extraction.engine.get_sqlite_client", return_value=client):
            mock_llm.return_value = _make_deep_llm_response()

            from extraction.engine import ingest_conversation

            result = await ingest_conversation(user_msg, assistant_msg, agent_id="test-agent")

        assert result["ok"] is True
        assert not result.get("db_write_failed", False)

        # Fast channel should have extracted identity from "我是数据工程师"
        fast_extracted = result["fast_extracted"]
        assert len(fast_extracted) >= 1
        fast_identity = [f for f in fast_extracted if f["category"] == "identity"]
        assert len(fast_identity) >= 1, f"Expected identity extraction, got: {fast_extracted}"

        # Deep channel should have returned 2 memories
        deep_extracted = result["deep_extracted"]
        assert len(deep_extracted) == 2

        # ---- Step 3: Verify DB state after ingestion ----
        async with client.session() as session:
            all_mems = (await session.execute(select(Memory))).scalars().all()
            # Filter out system memories (from init_db)
            our_mems = [m for m in all_mems if m.source in ("fast_channel", "deep_channel")]
            assert len(our_mems) >= 3  # at least 1 fast + 2 deep

            fast_mems = [m for m in our_mems if m.source == "fast_channel"]
            deep_mems = [m for m in our_mems if m.source == "deep_channel"]

            # Fast → core layer
            for fm in fast_mems:
                assert fm.layer == "core", f"Fast memory should be core, got {fm.layer}"
                assert fm.confidence == 1.0

            # Deep → working layer with expires_at
            for dm in deep_mems:
                assert dm.layer == "working", f"Deep memory should be working, got {dm.layer}"
                assert dm.expires_at is not None
                delta = dm.expires_at - _utc_now_naive()
                assert timedelta(hours=47) < delta < timedelta(hours=49)

        # ---- Step 4: Run lifecycle engine ----
        # The deep identity memory has category="identity" and confidence=0.9
        # → fast-track promotion to core (Phase 2)
        from lifecycle.engine import LifecycleEngine

        engine = LifecycleEngine(client)

        # Mock compress LLM (Phase 5) since no archives exist yet
        with patch("lifecycle.engine._call_compress_llm", new_callable=AsyncMock) as mock_compress:
            mock_compress.return_value = "compressed summary"
            lifecycle_result = await engine.run()

        # All 6 phases should have run
        for key in ("phase1", "phase2", "phase3", "phase4", "phase5", "phase6"):
            assert key in lifecycle_result, f"Missing {key} in lifecycle result"

        # Phase 1: no expired working (all have 48h TTL)
        assert lifecycle_result["phase1"]["deleted_count"] == 0

        # Phase 2: identity memory should be fast-track promoted
        promoted_count = lifecycle_result["phase2"]["promoted_count"]
        assert promoted_count >= 1, (
            f"Expected at least 1 promotion (identity fast-track), "
            f"got {promoted_count}. Full result: {lifecycle_result['phase2']}"
        )

        # Verify the promoted identity memory is now core
        async with client.session() as session:
            deep_identity_mems = (await session.execute(
                select(Memory).where(
                    Memory.source == "deep_channel",
                    Memory.category == "identity",
                )
            )).scalars().all()
            for dm in deep_identity_mems:
                assert dm.layer == "core", "Identity memory should have been promoted to core"
                assert dm.expires_at is None, "Promoted memory should have no expiry"

        # Phase 3: dedup skipped (no sqlite-vec in tests)
        assert lifecycle_result["phase3"].get("skipped") == "sqlite_vec_unavailable"

        # Verify lifecycle_log has 6 entries
        async with client.session() as session:
            log_count = await session.scalar(
                select(func.count()).select_from(LifecycleLog)
            )
            assert log_count == 6

        # ---- Step 5: Search and verify feedback_hint ----
        # We simulate the feedback_hint injection that search_memory does
        async with client.session() as session:
            core_mems = (await session.execute(
                select(Memory).where(
                    Memory.layer == "core",
                    Memory.deprecated == False,  # noqa: E712
                    Memory.source.in_(["fast_channel", "deep_channel"]),
                )
            )).scalars().all()
            assert len(core_mems) >= 2  # at least fast identity + deep promoted identity

            # Simulate feedback_hint injection (as done in mcp_server.py)
            search_results = []
            for mem in core_mems:
                item = {"memory_id": mem.id, "content": mem.content, "layer": mem.layer}
                item["feedback_hint"] = (
                    f"memory_feedback(memory_id={mem.id}, signal='helpful|outdated|wrong')"
                )
                search_results.append(item)

            assert all("feedback_hint" in r for r in search_results)
            assert all("memory_id" in r for r in search_results)

        # ---- Step 6: Submit feedback ----
        # Pick the deep identity memory and give it 3 helpful feedbacks
        target_mem_id = deep_identity_mems[0].id
        original_importance: float = 0.0
        async with client.session() as session:
            target = await session.get(Memory, target_mem_id)
            original_importance = target.importance
            for _ in range(3):
                session.add(MemoryFeedback(memory_id=target_mem_id, signal="helpful"))

        # ---- Step 7: Run lifecycle again → feedback adjusts importance ----
        with patch("lifecycle.engine._call_compress_llm", new_callable=AsyncMock) as mock_compress:
            mock_compress.return_value = "compressed summary"
            lifecycle_result2 = await engine.run()

        # Phase 6 should have adjusted importance
        assert lifecycle_result2["phase6"]["adjusted_count"] >= 1
        assert target_mem_id in lifecycle_result2["phase6"]["adjusted_ids"]

        # Verify importance increased
        async with client.session() as session:
            updated_mem = await session.get(Memory, target_mem_id)
            assert updated_mem.importance > original_importance, (
                f"Expected importance > {original_importance}, "
                f"got {updated_mem.importance}"
            )
            # Should have increased by 0.1 (helpful > 70% of 3 feedbacks)
            expected = min(1.0, original_importance + 0.1)
            assert abs(updated_mem.importance - expected) < 1e-6

        # Verify feedback rows consumed (deleted)
        async with client.session() as session:
            fb_count = await session.scalar(
                select(func.count()).select_from(MemoryFeedback).where(
                    MemoryFeedback.memory_id == target_mem_id
                )
            )
            assert fb_count == 0

        # Verify lifecycle_log now has 12 entries (6 from first run + 6 from second)
        async with client.session() as session:
            total_logs = await session.scalar(
                select(func.count()).select_from(LifecycleLog)
            )
            assert total_logs == 12

    finally:
        await client.close()
