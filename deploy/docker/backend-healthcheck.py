#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.request


def main() -> int:
    url = str(os.getenv("MEMORY_PALACE_BACKEND_HEALTHCHECK_URL") or "").strip()
    if not url:
        url = "http://127.0.0.1:8000/health"

    headers = {}
    api_key = str(os.getenv("MCP_API_KEY") or "").strip()
    if api_key:
        headers["X-MCP-API-Key"] = api_key

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("status") != "ok":
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
