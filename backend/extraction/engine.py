"""Extraction engine — orchestrates fast + deep channels, dedup, DB writes.

Public API:
    ingest_conversation(user_message, assistant_message, agent_id=None) -> Dict
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from extraction.fast_channel import extract_fast
from extraction.deep_channel import extract_deep
from db.sqlite_client import get_sqlite_client, Memory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dedup cache: MD5 hash → timestamp (epoch seconds)
# ---------------------------------------------------------------------------

_dedup_cache: Dict[str, float] = {}


def _env_bool(name: str, default: bool = True) -> bool:
    """Read an env var as a boolean (true/1/yes → True)."""
    val = os.environ.get(name, str(default)).lower()
    return val in ("true", "1", "yes")


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def _compute_dedup_key(agent_id: Optional[str], user_msg: str, assistant_msg: str) -> str:
    """MD5 of agent_id|||user_msg|||assistant_msg."""
    raw = f"{agent_id or ''}|||{user_msg}|||{assistant_msg}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _is_duplicate(key: str, window_sec: int) -> bool:
    """Check if key was seen within the dedup window."""
    ts = _dedup_cache.get(key)
    if ts is None:
        return False
    return (time.time() - ts) < window_sec


# ---------------------------------------------------------------------------
# DB writes
# ---------------------------------------------------------------------------

async def _write_memories(
    fast_results: List[Dict[str, Any]],
    deep_results: List[Dict[str, Any]],
) -> None:
    """Write extracted memories directly to DB via SQLAlchemy session.

    - Fast channel results → layer='core', confidence=1.0
    - Deep channel results → layer='working', expires_at=now+48h
    """
    client = get_sqlite_client()
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC
    expires_48h = now + timedelta(hours=48)

    async with client.session() as session:
        for item in fast_results:
            mem = Memory(
                content=item["content"],
                layer="core",
                confidence=item.get("confidence", 1.0),
                category=item.get("category"),
                source="fast_channel",
                importance=item.get("importance", 0.5),
            )
            session.add(mem)

        for item in deep_results:
            mem = Memory(
                content=item["content"],
                layer="working",
                confidence=item.get("confidence", 0.5),
                category=item.get("category"),
                source="deep_channel",
                importance=item.get("importance", 0.5),
                expires_at=expires_48h,
            )
            session.add(mem)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def ingest_conversation(
    user_message: str,
    assistant_message: str,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Orchestrate extraction from a conversation turn.

    1. Check env flags
    2. Dedup check
    3. Run fast channel (sync)
    4. Run deep channel (async)
    5. Write results to DB
    6. Return summary

    Returns:
        {ok: bool, fast_extracted: list, deep_extracted: list, skipped_reason?: str}
    """
    # --- Master switch ---
    if not _env_bool("EXTRACTION_ENABLED", True):
        return {"ok": False, "fast_extracted": [], "deep_extracted": [], "skipped_reason": "disabled"}

    fast_enabled = _env_bool("EXTRACTION_FAST_ENABLED", True)
    deep_enabled = _env_bool("EXTRACTION_DEEP_ENABLED", True)
    dedup_window = _env_int("EXTRACTION_DEDUP_WINDOW_SEC", 600)

    # --- Dedup ---
    dedup_key = _compute_dedup_key(agent_id, user_message, assistant_message)
    if _is_duplicate(dedup_key, dedup_window):
        return {"ok": False, "fast_extracted": [], "deep_extracted": [], "skipped_reason": "dedup"}

    # Record this conversation in dedup cache
    _dedup_cache[dedup_key] = time.time()

    # --- Fast channel (sync) ---
    fast_results: List[Dict[str, Any]] = []
    if fast_enabled:
        try:
            # Run on both user and assistant messages
            fast_results = extract_fast(user_message, role="user")
            fast_results += extract_fast(assistant_message, role="assistant")
        except Exception:
            logger.exception("fast_channel extraction failed")

    # --- Deep channel (async) ---
    deep_results: List[Dict[str, Any]] = []
    if deep_enabled:
        try:
            deep_results = await extract_deep(user_message, assistant_message)
        except Exception:
            logger.exception("deep_channel extraction failed")

    # --- Write to DB ---
    if fast_results or deep_results:
        try:
            await _write_memories(fast_results, deep_results)
        except Exception:
            logger.exception("Failed to write extracted memories to DB")

    return {
        "ok": True,
        "fast_extracted": fast_results,
        "deep_extracted": deep_results,
    }
