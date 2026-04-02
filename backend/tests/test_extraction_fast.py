"""Tests for fast_channel regex-based extraction."""

import pytest

from extraction.fast_channel import extract_fast


class TestExtractFastUserMessages:
    def test_identity_chinese(self):
        results = extract_fast("我是一名数据科学家", role="user")
        assert len(results) >= 1
        match = next(r for r in results if r["category"] == "identity")
        assert match["confidence"] == 1.0
        assert match["source"] == "fast_channel"

    def test_constraint_english(self):
        results = extract_fast("Don't ever use rm", role="user")
        assert len(results) >= 1
        match = next(r for r in results if r["category"] == "constraint")
        assert match["confidence"] == 1.0
        assert match["source"] == "fast_channel"

    def test_preference_chinese(self):
        results = extract_fast("记住我喜欢简洁回复", role="user")
        assert len(results) >= 1
        match = next(r for r in results if r["category"] == "preference")
        assert match["confidence"] == 1.0
        assert match["source"] == "fast_channel"

    def test_correction(self):
        results = extract_fast("其实那个API废弃了", role="user")
        assert len(results) >= 1
        match = next(r for r in results if r["category"] == "correction")
        assert match["confidence"] == 1.0
        assert match["source"] == "fast_channel"

    def test_no_match(self):
        results = extract_fast("今天天气不错", role="user")
        assert results == []

    def test_multiple_matches(self):
        results = extract_fast("我是工程师，不要用JS", role="user")
        categories = {r["category"] for r in results}
        assert "identity" in categories
        assert "constraint" in categories
        assert len(results) >= 2


class TestExtractFastAssistantMessages:
    def test_assistant_produces_agent_category(self):
        results = extract_fast("I noticed you prefer concise replies", role="assistant")
        assert len(results) >= 1
        assert all(r["category"].startswith("agent_") for r in results)

    def test_assistant_chinese(self):
        results = extract_fast("你似乎偏好用Python", role="assistant")
        assert len(results) >= 1
        assert all(r["category"].startswith("agent_") for r in results)


class TestExtractFastEdgeCases:
    def test_returns_list(self):
        result = extract_fast("hello world", role="user")
        assert isinstance(result, list)

    def test_default_role_is_user(self):
        results = extract_fast("我是工程师")
        assert len(results) >= 1
        assert results[0]["category"] == "identity"
