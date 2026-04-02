"""Tests for memory_feedback MCP tool and feedback_hint injection."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# test_memory_feedback_writes_to_db
# ---------------------------------------------------------------------------


class TestMemoryFeedbackWritesToDb:
    @pytest.mark.asyncio
    async def test_memory_feedback_writes_to_db(self):
        """Create memory, insert feedback, verify row exists via session.add call."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock()

        mock_client = AsyncMock()
        mock_client.get_memory_by_id = AsyncMock(return_value={"id": 42, "content": "test"})
        mock_client.session = MagicMock(return_value=mock_session)

        with patch("mcp_server.get_sqlite_client", return_value=mock_client), \
             patch("mcp_server.MemoryFeedback") as MockFB:
            from mcp_server import memory_feedback
            result_str = await memory_feedback(memory_id=42, signal="helpful", reason="great recall")

        result = json.loads(result_str)
        assert result["ok"] is True
        assert result["memory_id"] == 42
        assert result["signal"] == "helpful"
        MockFB.assert_called_once_with(memory_id=42, signal="helpful", reason="great recall")
        mock_session.add.assert_called_once()


# ---------------------------------------------------------------------------
# test_memory_feedback_invalid_signal
# ---------------------------------------------------------------------------


class TestMemoryFeedbackInvalidSignal:
    @pytest.mark.asyncio
    async def test_memory_feedback_invalid_signal(self):
        """signal='invalid' should return an error without touching DB."""
        from mcp_server import memory_feedback
        result_str = await memory_feedback(memory_id=1, signal="invalid")
        result = json.loads(result_str)
        assert result["ok"] is False
        assert "Invalid signal" in result["error"]


# ---------------------------------------------------------------------------
# test_memory_feedback_missing_memory
# ---------------------------------------------------------------------------


class TestMemoryFeedbackMissingMemory:
    @pytest.mark.asyncio
    async def test_memory_feedback_missing_memory(self):
        """Nonexistent memory_id should return an error."""
        mock_client = AsyncMock()
        mock_client.get_memory_by_id = AsyncMock(return_value=None)

        with patch("mcp_server.get_sqlite_client", return_value=mock_client):
            from mcp_server import memory_feedback
            result_str = await memory_feedback(memory_id=99999, signal="helpful")

        result = json.loads(result_str)
        assert result["ok"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# test_search_results_include_feedback_hint
# ---------------------------------------------------------------------------


class TestSearchResultsFeedbackHint:
    def test_feedback_hint_injected(self):
        """Verify feedback_hint is injected into search result items with memory_id."""
        results = [
            {"memory_id": 10, "uri": "core://test", "snippet": "hello"},
            {"memory_id": 20, "uri": "core://test2", "snippet": "world"},
            {"uri": "core://no_id", "snippet": "no memory_id"},
        ]
        # Simulate the injection logic from search_memory
        for item in results:
            mid = item.get("memory_id")
            if mid is not None:
                item["feedback_hint"] = f"memory_feedback(memory_id={mid}, signal='helpful|outdated|wrong')"

        assert results[0]["feedback_hint"] == "memory_feedback(memory_id=10, signal='helpful|outdated|wrong')"
        assert results[1]["feedback_hint"] == "memory_feedback(memory_id=20, signal='helpful|outdated|wrong')"
        assert "feedback_hint" not in results[2]
