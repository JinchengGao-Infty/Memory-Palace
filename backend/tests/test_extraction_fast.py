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


class TestExtractFastFalsePositives:
    """Regression tests for false positive patterns."""

    def test_actually_in_sentence_no_match(self):
        results = extract_fast("I actually went to the store", role="user")
        correction_results = [r for r in results if r["category"] == "correction"]
        assert correction_results == []

    def test_remember_question_no_match(self):
        results = extract_fast("Do you remember what I said?", role="user")
        preference_results = [r for r in results if r["category"] == "preference"]
        assert preference_results == []

    def test_wo_shi_shuo_no_match(self):
        results = extract_fast("我是说你应该用Python", role="user")
        identity_results = [r for r in results if r["category"] == "identity"]
        assert identity_results == []

    def test_constraint_stops_at_punctuation(self):
        results = extract_fast("不要用rm，其他都行", role="user")
        match = next(r for r in results if r["category"] == "constraint")
        assert "其他都行" not in match["content"]
        assert "用rm" in match["content"]

    def test_actually_with_comma_matches(self):
        """'actually,' at sentence start should still match correction."""
        results = extract_fast("Actually, that API is deprecated", role="user")
        correction_results = [r for r in results if r["category"] == "correction"]
        assert len(correction_results) >= 1

    def test_remember_that_matches(self):
        """'remember that' should still match preference."""
        results = extract_fast("remember that I like Python", role="user")
        preference_results = [r for r in results if r["category"] == "preference"]
        assert len(preference_results) >= 1

    def test_remember_to_matches(self):
        """'remember to' should still match preference."""
        results = extract_fast("remember to use trash instead of rm", role="user")
        preference_results = [r for r in results if r["category"] == "preference"]
        assert len(preference_results) >= 1


class TestExtractFastEdgeCases:
    def test_returns_list(self):
        result = extract_fast("hello world", role="user")
        assert isinstance(result, list)

    def test_default_role_is_user(self):
        results = extract_fast("我是工程师")
        assert len(results) >= 1
        assert results[0]["category"] == "identity"
