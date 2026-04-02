"""Fast channel extraction — regex-only, zero LLM calls.

Pure function: no DB writes, no network I/O.
Hot-reloadable: patterns.json is re-read when its mtime changes.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_PATTERNS_PATH = Path(__file__).parent / "patterns.json"

# Cache: (mtime, parsed_data)
_cache: Tuple[float, Dict[str, Any]] | None = None


def _load_patterns() -> Dict[str, Any]:
    """Load patterns from JSON with hot-reload based on file mtime."""
    global _cache
    mtime = os.path.getmtime(_PATTERNS_PATH)
    if _cache is not None and _cache[0] == mtime:
        return _cache[1]
    with open(_PATTERNS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Pre-compile regexes
    for key in ("user_patterns", "assistant_patterns"):
        for entry in data.get(key, []):
            entry["_compiled"] = [re.compile(p) for p in entry["patterns"]]
    _cache = (mtime, data)
    return data


def extract_fast(
    message: str, role: str = "user"
) -> List[Dict[str, Any]]:
    """Extract memory-worthy fragments from a message using regex patterns.

    Args:
        message: The text to scan.
        role: "user" or "assistant" — determines which pattern set to use.

    Returns:
        List of dicts with keys: content, category, confidence, source.
        Empty list if no patterns match.
    """
    data = _load_patterns()
    pattern_key = "assistant_patterns" if role == "assistant" else "user_patterns"
    pattern_groups = data.get(pattern_key, [])

    results: List[Dict[str, Any]] = []
    used_spans: List[Tuple[int, int]] = []

    for group in pattern_groups:
        category = group["category"]
        extract_group = group.get("extract_group", 0)
        compiled = group.get("_compiled", [])

        for regex in compiled:
            for m in regex.finditer(message):
                span = m.span()
                # Skip overlapping matches
                if any(_overlaps(span, used) for used in used_spans):
                    continue
                used_spans.append(span)
                content = m.group(extract_group).strip() if extract_group > 0 else m.group(0).strip()
                results.append(
                    {
                        "content": content,
                        "category": category,
                        "confidence": 1.0,
                        "source": "fast_channel",
                    }
                )
                break  # One match per regex is enough; move to next regex

    return results


def _overlaps(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    """Check if two spans overlap."""
    return a[0] < b[1] and b[0] < a[1]
