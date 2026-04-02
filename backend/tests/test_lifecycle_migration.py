"""Tests for lifecycle migration (0004) — new columns, tables, and defaults."""

from pathlib import Path

import pytest
from sqlalchemy import select, text

from db.sqlite_client import Memory, SQLiteClient


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.mark.asyncio
async def test_migration_adds_lifecycle_columns(tmp_path: Path) -> None:
    """New memory should have correct lifecycle field defaults."""
    db_path = tmp_path / "lifecycle.db"
    client = SQLiteClient(_sqlite_url(db_path))
    await client.init_db()

    created = await client.create_memory(
        parent_path="",
        content="Lifecycle test memory",
        priority=1,
        title="lifecycle-test",
        domain="core",
    )

    async with client.session() as session:
        memory = await session.get(Memory, created["id"])
        assert memory is not None
        assert memory.layer == "core"
        assert memory.importance == pytest.approx(0.5)
        assert memory.source == "manual"
        assert memory.confidence == pytest.approx(1.0)
        assert memory.category is None
        assert memory.expires_at is None

    await client.close()


@pytest.mark.asyncio
async def test_memory_feedback_table_exists(tmp_path: Path) -> None:
    """memory_feedback table should exist and be queryable."""
    db_path = tmp_path / "lifecycle-feedback.db"
    client = SQLiteClient(_sqlite_url(db_path))
    await client.init_db()

    async with client.session() as session:
        result = await session.execute(text("SELECT * FROM memory_feedback"))
        rows = result.fetchall()
        assert rows == []

    await client.close()


@pytest.mark.asyncio
async def test_lifecycle_log_table_exists(tmp_path: Path) -> None:
    """lifecycle_log table should exist and be queryable."""
    db_path = tmp_path / "lifecycle-log.db"
    client = SQLiteClient(_sqlite_url(db_path))
    await client.init_db()

    async with client.session() as session:
        result = await session.execute(text("SELECT * FROM lifecycle_log"))
        rows = result.fetchall()
        assert rows == []

    await client.close()
