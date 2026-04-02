"""Tests for deep_channel LLM-based extraction."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from extraction.deep_channel import (
    AGENT_CATEGORIES,
    USER_CATEGORIES,
    VALID_CATEGORIES,
    extract_deep,
)


class TestValidCategories:
    def test_user_categories_has_at_least_10(self):
        assert len(USER_CATEGORIES) >= 10

    def test_agent_categories_has_at_least_3(self):
        assert len(AGENT_CATEGORIES) >= 3

    def test_valid_categories_is_union(self):
        assert VALID_CATEGORIES == USER_CATEGORIES | AGENT_CATEGORIES


class TestExtractDeep:
    @pytest.mark.asyncio
    @patch("extraction.deep_channel._call_llm", new_callable=AsyncMock)
    async def test_returns_structured_results(self, mock_llm):
        mock_llm.return_value = json.dumps(
            {
                "memories": [
                    {
                        "content": "User prefers Python",
                        "category": "preference",
                        "importance": 0.8,
                        "confidence": 0.9,
                        "attributed_to": "user",
                    }
                ]
            }
        )
        results = await extract_deep("I really like Python", "Noted!")
        assert len(results) == 1
        r = results[0]
        assert r["content"] == "User prefers Python"
        assert r["category"] == "preference"
        assert r["importance"] == 0.8
        assert r["confidence"] == 0.9
        assert r["source"] == "deep_channel"
        assert r["_attributed_to"] == "user"

    @pytest.mark.asyncio
    @patch("extraction.deep_channel._call_llm", new_callable=AsyncMock)
    async def test_enforces_attribution(self, mock_llm):
        """Assistant-attributed memory with user category should be remapped."""
        mock_llm.return_value = json.dumps(
            {
                "memories": [
                    {
                        "content": "User likes dark mode",
                        "category": "preference",
                        "importance": 0.7,
                        "confidence": 0.8,
                        "attributed_to": "assistant",
                    }
                ]
            }
        )
        results = await extract_deep("I like dark mode", "Got it!")
        assert len(results) == 1
        assert results[0]["category"] == "agent_user_habit"

    @pytest.mark.asyncio
    @patch("extraction.deep_channel._call_llm", new_callable=AsyncMock)
    async def test_llm_timeout_returns_empty(self, mock_llm):
        mock_llm.side_effect = TimeoutError("LLM timed out")
        results = await extract_deep("Hello", "Hi")
        assert results == []

    @pytest.mark.asyncio
    @patch("extraction.deep_channel._call_llm", new_callable=AsyncMock)
    async def test_invalid_json_returns_empty(self, mock_llm):
        mock_llm.return_value = "this is not json at all {{{garbage"
        results = await extract_deep("Hello", "Hi")
        assert results == []

    @pytest.mark.asyncio
    @patch("extraction.deep_channel._call_llm", new_callable=AsyncMock)
    async def test_clamps_importance_and_confidence(self, mock_llm):
        mock_llm.return_value = json.dumps(
            {
                "memories": [
                    {
                        "content": "Test",
                        "category": "fact",
                        "importance": 1.5,
                        "confidence": -0.2,
                        "attributed_to": "user",
                    }
                ]
            }
        )
        results = await extract_deep("Test", "OK")
        assert results[0]["importance"] == 1.0
        assert results[0]["confidence"] == 0.0

    @pytest.mark.asyncio
    @patch("extraction.deep_channel._call_llm", new_callable=AsyncMock)
    async def test_invalid_category_filtered(self, mock_llm):
        mock_llm.return_value = json.dumps(
            {
                "memories": [
                    {
                        "content": "Test",
                        "category": "nonexistent_category",
                        "importance": 0.5,
                        "confidence": 0.5,
                        "attributed_to": "user",
                    }
                ]
            }
        )
        results = await extract_deep("Test", "OK")
        assert results == []
