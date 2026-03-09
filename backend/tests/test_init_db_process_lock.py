import asyncio
from pathlib import Path

import pytest

from db.sqlite_client import SQLiteClient, _extract_sqlite_file_path, _resolve_init_lock_path


@pytest.mark.asyncio
async def test_init_db_serializes_same_database_bootstrap(monkeypatch, tmp_path):
    database_path = tmp_path / "init-lock.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    client_a = SQLiteClient(database_url)
    client_b = SQLiteClient(database_url)

    concurrency_lock = asyncio.Lock()
    current_concurrency = 0
    max_concurrency = 0

    async def fake_unlocked_init(self):
        nonlocal current_concurrency, max_concurrency
        async with concurrency_lock:
            current_concurrency += 1
            max_concurrency = max(max_concurrency, current_concurrency)
        await asyncio.sleep(0.05)
        async with concurrency_lock:
            current_concurrency -= 1

    monkeypatch.setattr(
        SQLiteClient, "_run_init_db_unlocked", fake_unlocked_init, raising=True
    )

    try:
        await asyncio.gather(client_a.init_db(), client_b.init_db())
    finally:
        await client_a.engine.dispose()
        await client_b.engine.dispose()

    assert max_concurrency == 1


def test_extract_sqlite_file_path_skips_memory_targets_and_query_string() -> None:
    relative = _extract_sqlite_file_path("sqlite+aiosqlite:///relative.db?cache=shared")
    absolute = _extract_sqlite_file_path("sqlite+aiosqlite:////tmp/demo.db?mode=rwc")
    memory_target = _extract_sqlite_file_path("sqlite+aiosqlite:///:memory:")
    shared_memory_target = _extract_sqlite_file_path(
        "sqlite+aiosqlite:///file::memory:?cache=shared"
    )

    assert relative == Path("relative.db")
    assert absolute == Path("/tmp/demo.db")
    assert memory_target is None
    assert shared_memory_target is None


def test_resolve_init_lock_path_uses_database_suffix() -> None:
    database_path = Path("/tmp/demo.db")

    assert _resolve_init_lock_path(database_path) == Path("/tmp/demo.db.init.lock")
