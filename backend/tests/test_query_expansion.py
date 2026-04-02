"""Tests for extraction.query_expansion module."""

import json
import math
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_httpx_client(variants: list[str]) -> MagicMock:
    """Build a mock that replaces httpx.AsyncClient as a context manager."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(variants)}}]
    }

    mock_post = AsyncMock(return_value=resp)
    mock_client = MagicMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls, mock_post


def _mock_httpx_client_error() -> MagicMock:
    """Build a mock that raises on post."""
    mock_post = AsyncMock(side_effect=Exception("timeout"))
    mock_client = MagicMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


# ---------------------------------------------------------------------------
# expand_query tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_short_query_expands_keywords():
    """Short query (<= 15 chars) should produce synonym keywords."""
    variants = ["编辑器", "editor", "代码编辑"]
    mock_cls, mock_post = _mock_httpx_client(variants)

    with patch.dict("os.environ", {"ROUTER_API_BASE": "http://fake:8000"}):
        with patch("extraction.query_expansion.QUERY_EXPANSION_ENABLED", True):
            with patch("extraction.query_expansion.httpx.AsyncClient", mock_cls):
                from extraction.query_expansion import expand_query
                result = await expand_query("编辑")

    assert result[0] == "编辑"
    assert "编辑器" in result
    assert "editor" in result
    assert "代码编辑" in result


@pytest.mark.asyncio
async def test_long_query_expands_rephrases():
    """Long query (> 15 chars) should produce up to 3 rephrased variants."""
    variants = [
        "How to configure VS Code for Python",
        "VS Code Python setup guide",
        "Setting up Python in Visual Studio Code",
    ]
    mock_cls, mock_post = _mock_httpx_client(variants)

    with patch.dict("os.environ", {"ROUTER_API_BASE": "http://fake:8000"}):
        with patch("extraction.query_expansion.QUERY_EXPANSION_ENABLED", True):
            with patch("extraction.query_expansion.httpx.AsyncClient", mock_cls):
                from extraction.query_expansion import expand_query
                result = await expand_query("how to set up Python development environment")

    assert result[0] == "how to set up Python development environment"
    assert len(result) <= 7  # original + up to 6
    # Check that the LLM was called with temperature 0.4 (long query)
    call_json = mock_post.call_args[1]["json"]
    assert call_json["temperature"] == 0.4


@pytest.mark.asyncio
async def test_cjk_adds_english():
    """CJK query prompt should include English keyword hint."""
    variants = ["内存管理", "memory management"]
    mock_cls, mock_post = _mock_httpx_client(variants)

    with patch.dict("os.environ", {"ROUTER_API_BASE": "http://fake:8000"}):
        with patch("extraction.query_expansion.QUERY_EXPANSION_ENABLED", True):
            with patch("extraction.query_expansion.httpx.AsyncClient", mock_cls):
                from extraction.query_expansion import expand_query
                await expand_query("内存管理")

    call_json = mock_post.call_args[1]["json"]
    system_msg = call_json["messages"][0]["content"]
    assert "English" in system_msg


@pytest.mark.asyncio
async def test_llm_failure_returns_original():
    """LLM errors should gracefully return [original_query]."""
    mock_cls = _mock_httpx_client_error()

    with patch.dict("os.environ", {"ROUTER_API_BASE": "http://fake:8000"}):
        with patch("extraction.query_expansion.QUERY_EXPANSION_ENABLED", True):
            with patch("extraction.query_expansion.httpx.AsyncClient", mock_cls):
                from extraction.query_expansion import expand_query
                result = await expand_query("test query")

    assert result == ["test query"]


@pytest.mark.asyncio
async def test_disabled_returns_original():
    """When QUERY_EXPANSION_ENABLED is False, return [original_query]."""
    with patch("extraction.query_expansion.QUERY_EXPANSION_ENABLED", False):
        from extraction.query_expansion import expand_query
        result = await expand_query("anything")

    assert result == ["anything"]


# ---------------------------------------------------------------------------
# apply_multi_hit_boost tests
# ---------------------------------------------------------------------------

def test_multi_hit_boost():
    """Memories hit by multiple variants should get score boosted."""
    from extraction.query_expansion import apply_multi_hit_boost

    variant_a = [
        {"memory_id": 1, "score": 0.9, "title": "A"},
        {"memory_id": 2, "score": 0.8, "title": "B"},
    ]
    variant_b = [
        {"memory_id": 1, "score": 0.85, "title": "A"},
        {"memory_id": 3, "score": 0.7, "title": "C"},
    ]

    merged = apply_multi_hit_boost([variant_a, variant_b])

    # memory_id=1 hit twice -> boosted (keeps best score 0.9)
    mem1 = next(r for r in merged if r["memory_id"] == 1)
    expected_boost = 1 + 0.1 * math.log(2)
    assert mem1["score"] == pytest.approx(0.9 * expected_boost)
    assert mem1["multi_hit_count"] == 2
    assert mem1["multi_hit_boost"] == pytest.approx(expected_boost)

    # memory_id=2 hit once -> no boost
    mem2 = next(r for r in merged if r["memory_id"] == 2)
    assert mem2["score"] == 0.8
    assert "multi_hit_count" not in mem2

    # memory_id=3 hit once -> no boost
    mem3 = next(r for r in merged if r["memory_id"] == 3)
    assert mem3["score"] == 0.7

    # Results sorted by score descending
    scores = [r["score"] for r in merged]
    assert scores == sorted(scores, reverse=True)


def test_multi_hit_boost_empty():
    """Empty input should return empty list."""
    from extraction.query_expansion import apply_multi_hit_boost
    assert apply_multi_hit_boost([]) == []
    assert apply_multi_hit_boost([[], []]) == []
