"""Query expansion via LLM for improved search recall."""

import json
import math
import logging
import os
import re
from typing import Any, Dict, List

import httpx

from shared_utils import env_bool

logger = logging.getLogger(__name__)

QUERY_EXPANSION_ENABLED = env_bool("QUERY_EXPANSION_ENABLED", True)
QUERY_EXPANSION_TIMEOUT_SEC = float(os.environ.get("QUERY_EXPANSION_TIMEOUT_SEC", "3"))
QUERY_EXPANSION_MIN_QUERY_LEN = int(os.environ.get("QUERY_EXPANSION_MIN_QUERY_LEN", "2"))


def _detect_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    return bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', text))


async def expand_query(query: str) -> List[str]:
    """
    Expand a search query with synonyms/rephrases via LLM.

    Short queries (<=15 chars): 4-6 synonym keywords, temp=0.2
    Long queries (>15 chars): up to 3 rephrased variants, temp=0.4
    CJK queries: prompt includes English keyword hint

    Returns [original_query] + expanded variants.
    On error: returns [original_query] only.
    """
    if not QUERY_EXPANSION_ENABLED:
        return [query]
    if len(query.strip()) < QUERY_EXPANSION_MIN_QUERY_LEN:
        return [query]

    is_short = len(query) <= 15
    is_cjk = _detect_cjk(query)

    if is_short:
        system = "Generate 4-6 search keyword synonyms/variations. Return ONLY a JSON array of strings."
        if is_cjk:
            system += " Include relevant English keywords."
        temperature = 0.2
    else:
        system = "Generate up to 3 rephrased search queries. Return ONLY a JSON array of strings."
        if is_cjk:
            system += " Include at least one English variant."
        temperature = 0.4

    user_prompt = f"Query: {query}"

    base_url = os.environ.get("ROUTER_API_BASE", "").rstrip("/")
    api_key = os.environ.get("ROUTER_API_KEY", "")
    if not base_url:
        return [query]

    try:
        async with httpx.AsyncClient(timeout=QUERY_EXPANSION_TIMEOUT_SEC) as client:
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": os.environ.get("EXTRACTION_DEEP_MODEL", "default"),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                },
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

            variants = json.loads(content)
            if not isinstance(variants, list):
                return [query]
            variants = [str(v).strip() for v in variants if v and str(v).strip()]
            return [query] + variants[:6]
    except Exception:
        logger.debug("Query expansion failed, using original query")
        return [query]


def apply_multi_hit_boost(results_by_variant: List[List[Dict]]) -> List[Dict]:
    """
    Merge results from multiple query variants.
    Memories hit by multiple variants get score boosted.

    boost = 1 + 0.1 * ln(hit_count) for hit_count > 1
    """
    hit_counts: Dict[int, int] = {}
    best_result: Dict[int, Dict] = {}

    for variant_results in results_by_variant:
        for item in variant_results:
            mid = item.get("memory_id")
            if mid is None:
                continue
            hit_counts[mid] = hit_counts.get(mid, 0) + 1
            existing = best_result.get(mid)
            if existing is None:
                best_result[mid] = dict(item)
            else:
                current_score = item.get("score", 0) or 0
                existing_score = existing.get("score", 0) or 0
                if current_score > existing_score:
                    best_result[mid] = dict(item)

    for mid, result in best_result.items():
        count = hit_counts.get(mid, 1)
        if count > 1:
            original_score = result.get("score", 0) or 0
            boost = 1 + 0.1 * math.log(count)
            result["score"] = original_score * boost
            result["multi_hit_count"] = count
            result["multi_hit_boost"] = boost

    merged = sorted(best_result.values(), key=lambda x: x.get("score", 0) or 0, reverse=True)
    return merged
