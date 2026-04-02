"""Deep channel extraction — LLM-based memory extraction.

Calls an OpenAI-compatible chat completions API to extract long-term-worthy
memories from conversation turns. Pure function: no DB writes.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category constants
# ---------------------------------------------------------------------------

USER_CATEGORIES: frozenset[str] = frozenset(
    {
        "identity",
        "preference",
        "decision",
        "constraint",
        "correction",
        "fact",
        "goal",
        "skill",
        "entity",
        "todo",
        "relationship",
        "insight",
        "project_state",
    }
)

AGENT_CATEGORIES: frozenset[str] = frozenset(
    {
        "agent_self_improvement",
        "agent_user_habit",
        "agent_relationship",
        "agent_persona",
    }
)

VALID_CATEGORIES: frozenset[str] = USER_CATEGORIES | AGENT_CATEGORIES

# ---------------------------------------------------------------------------
# LLM interaction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a memory extraction module. Given a user message and an assistant reply,
extract facts worth remembering long-term. Output ONLY valid JSON:

{"memories": [
  {
    "content": "<concise fact>",
    "category": "<one of: identity, preference, decision, constraint, correction, fact, goal, skill, entity, todo, relationship, insight, project_state, agent_self_improvement, agent_user_habit, agent_relationship, agent_persona>",
    "importance": <0.0-1.0>,
    "confidence": <0.0-1.0>,
    "attributed_to": "<user|assistant>"
  }
]}

Rules:
- Only extract facts that are long-term worthy (not ephemeral).
- attributed_to="user" for things the user stated about themselves.
- attributed_to="assistant" ONLY for agent_* categories (self-improvement, observations about user habits, relationship notes, persona adjustments).
- If nothing is worth remembering, return {"memories": []}.
- Do NOT wrap in markdown code fences.
"""


def _build_user_prompt(user_msg: str, assistant_msg: str) -> str:
    """Build the user prompt with a dynamic token budget hint."""
    total_len = len(user_msg) + len(assistant_msg)
    max_memories = min(5, max(1, total_len // 200))
    return (
        f"Extract up to {max_memories} memories from this exchange.\n\n"
        f"User: {user_msg}\n\n"
        f"Assistant: {assistant_msg}"
    )


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Synchronous call to OpenAI-compatible chat completions API.

    Returns the raw text content from the LLM response.
    Raises TimeoutError or httpx errors on failure.
    """
    base_url = os.environ.get("ROUTER_API_BASE", "http://localhost:8080")
    api_key = os.environ.get("ROUTER_API_KEY", "")
    timeout_sec = int(os.environ.get("EXTRACTION_DEEP_TIMEOUT_SEC", "5"))

    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except httpx.TimeoutException as exc:
        raise TimeoutError(str(exc)) from exc


def _repair_json(raw: str) -> str:
    """Attempt light JSON repair: strip fences, trailing commas, etc."""
    # Strip markdown code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw.strip())
    # Remove trailing commas before } or ]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw


def _parse_memories(raw: str) -> List[Dict[str, Any]]:
    """Parse LLM output into a list of memory dicts."""
    repaired = _repair_json(raw)
    data = json.loads(repaired)
    if isinstance(data, dict) and "memories" in data:
        return data["memories"]
    return []


async def extract_deep(
    user_message: str, assistant_message: str
) -> List[Dict[str, Any]]:
    """Extract memories from a conversation turn using LLM.

    Returns a list of dicts with keys:
        content, category, importance, confidence, source, _attributed_to

    On any error (timeout, bad JSON, etc.) returns [].
    """
    try:
        user_prompt = _build_user_prompt(user_message, assistant_message)
        raw = _call_llm(_SYSTEM_PROMPT, user_prompt)
        memories = _parse_memories(raw)
    except (TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.debug("deep_channel extraction failed: %s", exc)
        return []

    results: List[Dict[str, Any]] = []
    for mem in memories:
        category = mem.get("category", "")
        attributed_to = mem.get("attributed_to", "user")
        content = mem.get("content", "")

        # Skip invalid categories
        if category not in VALID_CATEGORIES:
            continue

        # Enforce attribution constraint
        if attributed_to == "assistant" and category not in AGENT_CATEGORIES:
            category = "agent_user_habit"

        # Clamp importance and confidence to [0, 1]
        importance = max(0.0, min(1.0, float(mem.get("importance", 0.5))))
        confidence = max(0.0, min(1.0, float(mem.get("confidence", 0.5))))

        results.append(
            {
                "content": content,
                "category": category,
                "importance": importance,
                "confidence": confidence,
                "source": "deep_channel",
                "_attributed_to": attributed_to,
            }
        )

    return results
