import pytest

import mcp_server


class _SystemViewClient:
    async def get_all_paths(self):
        return [
            {
                "domain": "core",
                "path": "agent/profile",
                "uri": "core://agent/profile",
                "memory_id": 7,
                "priority": 2,
            }
        ]

    async def get_recent_memories(self, limit: int = 10):
        _ = limit
        return [
            {
                "uri": "core://agent/profile",
                "priority": 2,
                "disclosure": "When I need the profile context",
                "created_at": "2026-03-01T11:22:33Z",
            }
        ]


@pytest.mark.asyncio
async def test_system_index_uses_utc_generated_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "get_sqlite_client", lambda: _SystemViewClient())
    monkeypatch.setattr(mcp_server, "_utc_iso_now", lambda: "2026-03-20T01:02:03Z")

    raw = await mcp_server.read_memory("system://index")

    assert "# Memory Index" in raw
    assert "# Generated: 2026-03-20T01:02:03Z" in raw
    assert "core://agent/profile [#7] [★2]" in raw


@pytest.mark.asyncio
async def test_system_recent_uses_same_utc_generated_timestamp_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "get_sqlite_client", lambda: _SystemViewClient())
    monkeypatch.setattr(mcp_server, "_utc_iso_now", lambda: "2026-03-20T01:02:03Z")

    raw = await mcp_server.read_memory("system://recent/3")

    assert "# Recently Modified Memories" in raw
    assert "# Generated: 2026-03-20T01:02:03Z" in raw
    assert "# Showing: 1 most recent entries (requested: 3)" in raw
    assert "1. core://agent/profile  [★2]  modified: 2026-03-01 11:22" in raw
