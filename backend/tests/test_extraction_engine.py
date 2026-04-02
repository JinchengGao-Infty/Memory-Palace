"""Tests for extraction engine — orchestrator + dedup."""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from extraction.engine import ingest_conversation, _dedup_cache, _compute_dedup_key


# ---------------------------------------------------------------------------
# Helpers — return fresh lists each call to avoid mutation issues
# ---------------------------------------------------------------------------

def _make_fast():
    return [
        {"content": "user likes Python", "category": "preference", "confidence": 1.0, "source": "fast_channel"},
    ]


def _make_deep():
    return [
        {
            "content": "user is a data scientist",
            "category": "identity",
            "importance": 0.8,
            "confidence": 0.9,
            "source": "deep_channel",
            "_attributed_to": "user",
        },
    ]


@pytest.fixture(autouse=True)
def _clear_dedup_cache():
    """Clear the dedup cache before each test."""
    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


# ---------------------------------------------------------------------------
# test_ingest_runs_both_channels
# ---------------------------------------------------------------------------

class TestIngestRunsBothChannels:
    @pytest.mark.asyncio
    async def test_ingest_runs_both_channels(self, monkeypatch):
        """Mock both channels, verify both called, results merged."""
        monkeypatch.setenv("EXTRACTION_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_FAST_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_DEEP_ENABLED", "true")

        with patch("extraction.engine.extract_fast", side_effect=lambda *a, **kw: _make_fast()) as mock_fast, \
             patch("extraction.engine.extract_deep", new_callable=AsyncMock, return_value=_make_deep()) as mock_deep, \
             patch("extraction.engine._write_memories", new_callable=AsyncMock, return_value=None):

            result = await ingest_conversation("hello", "hi there", agent_id="test-agent")

            assert result["ok"] is True
            # fast is called for both user and assistant roles → 2x results
            assert len(result["fast_extracted"]) == 2
            assert len(result["deep_extracted"]) == 1
            assert result["fast_extracted"][0]["content"] == "user likes Python"
            assert result["deep_extracted"][0]["content"] == "user is a data scientist"

            assert mock_fast.call_count == 2  # user + assistant
            mock_deep.assert_called_once_with("hello", "hi there")


# ---------------------------------------------------------------------------
# test_dedup_skips_duplicate_within_window
# ---------------------------------------------------------------------------

class TestDedupSkipsDuplicateWithinWindow:
    @pytest.mark.asyncio
    async def test_dedup_skips_duplicate_within_window(self, monkeypatch):
        """Same message twice within 10min → second returns skipped_reason."""
        monkeypatch.setenv("EXTRACTION_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_DEDUP_WINDOW_SEC", "600")

        with patch("extraction.engine.extract_fast", side_effect=lambda *a, **kw: _make_fast()), \
             patch("extraction.engine.extract_deep", new_callable=AsyncMock, return_value=_make_deep()), \
             patch("extraction.engine._write_memories", new_callable=AsyncMock, return_value=None):

            r1 = await ingest_conversation("hello", "hi there", agent_id="a1")
            assert r1["ok"] is True

            r2 = await ingest_conversation("hello", "hi there", agent_id="a1")
            assert r2["ok"] is False
            assert "dedup" in r2["skipped_reason"]


# ---------------------------------------------------------------------------
# test_dedup_allows_after_window
# ---------------------------------------------------------------------------

class TestDedupAllowsAfterWindow:
    @pytest.mark.asyncio
    async def test_dedup_allows_after_window(self, monkeypatch):
        """Same message after window expires → processed."""
        monkeypatch.setenv("EXTRACTION_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_DEDUP_WINDOW_SEC", "600")

        with patch("extraction.engine.extract_fast", side_effect=lambda *a, **kw: _make_fast()), \
             patch("extraction.engine.extract_deep", new_callable=AsyncMock, return_value=_make_deep()), \
             patch("extraction.engine._write_memories", new_callable=AsyncMock, return_value=None):

            r1 = await ingest_conversation("hello", "hi there", agent_id="a1")
            assert r1["ok"] is True

            # Manually expire the dedup entry
            key = _compute_dedup_key("a1", "hello", "hi there")
            _dedup_cache[key] = time.time() - 700  # 700s ago, past 600s window

            r2 = await ingest_conversation("hello", "hi there", agent_id="a1")
            assert r2["ok"] is True


# ---------------------------------------------------------------------------
# test_fast_only_when_deep_disabled
# ---------------------------------------------------------------------------

class TestFastOnlyWhenDeepDisabled:
    @pytest.mark.asyncio
    async def test_fast_only_when_deep_disabled(self, monkeypatch):
        """Set EXTRACTION_DEEP_ENABLED=false → only fast results."""
        monkeypatch.setenv("EXTRACTION_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_FAST_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_DEEP_ENABLED", "false")

        with patch("extraction.engine.extract_fast", side_effect=lambda *a, **kw: _make_fast()) as mock_fast, \
             patch("extraction.engine.extract_deep", new_callable=AsyncMock, return_value=_make_deep()) as mock_deep, \
             patch("extraction.engine._write_memories", new_callable=AsyncMock, return_value=None):

            result = await ingest_conversation("hello", "hi there")

            assert result["ok"] is True
            assert len(result["fast_extracted"]) == 2  # user + assistant
            assert len(result["deep_extracted"]) == 0
            mock_fast.assert_called()
            mock_deep.assert_not_called()


# ---------------------------------------------------------------------------
# test_disabled_returns_early
# ---------------------------------------------------------------------------

class TestDisabledReturnsEarly:
    @pytest.mark.asyncio
    async def test_disabled_returns_early(self, monkeypatch):
        """Set EXTRACTION_ENABLED=false → returns {ok: false, skipped_reason: 'disabled'}."""
        monkeypatch.setenv("EXTRACTION_ENABLED", "false")

        result = await ingest_conversation("hello", "hi there")

        assert result["ok"] is False
        assert result["skipped_reason"] == "disabled"


# ---------------------------------------------------------------------------
# test_writes_to_db
# ---------------------------------------------------------------------------

class TestWritesToDB:
    @pytest.mark.asyncio
    async def test_writes_to_db(self, tmp_path, monkeypatch):
        """Verify extracted memories written to DB with correct layer/expires_at."""
        db_path = tmp_path / "test.db"
        db_url = f"sqlite+aiosqlite:///{db_path}"

        monkeypatch.setenv("EXTRACTION_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_FAST_ENABLED", "true")
        monkeypatch.setenv("EXTRACTION_DEEP_ENABLED", "true")

        # Create a real SQLiteClient with tmp db
        from db.sqlite_client import SQLiteClient, Memory

        client = SQLiteClient(db_url)
        await client.init_db()

        with patch("extraction.engine.extract_fast", side_effect=lambda *a, **kw: _make_fast()), \
             patch("extraction.engine.extract_deep", new_callable=AsyncMock, return_value=_make_deep()), \
             patch("extraction.engine.get_sqlite_client", return_value=client):

            result = await ingest_conversation("hello", "hi there", agent_id="test-agent")

            assert result["ok"] is True

        # Verify DB contents
        from sqlalchemy import select
        async with client.session() as session:
            memories = (await session.execute(select(Memory))).scalars().all()
            assert len(memories) >= 2  # at least 1 fast + 1 deep

            fast_mems = [m for m in memories if m.source == "fast_channel"]
            assert len(fast_mems) >= 1
            fast_mem = fast_mems[0]
            assert fast_mem.layer == "core"
            assert fast_mem.confidence == 1.0

            deep_mems = [m for m in memories if m.source == "deep_channel"]
            assert len(deep_mems) == 1
            deep_mem = deep_mems[0]
            assert deep_mem.layer == "working"
            assert deep_mem.expires_at is not None
            # expires_at should be roughly 48h from now
            delta = deep_mem.expires_at - datetime.now(timezone.utc).replace(tzinfo=None)
            assert timedelta(hours=47) < delta < timedelta(hours=49)
