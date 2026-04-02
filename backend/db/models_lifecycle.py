"""ORM models for lifecycle-related tables (migration 0004)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, text

from db.sqlite_client import Base


class MemoryFeedback(Base):
    """User feedback signal on a memory."""

    __tablename__ = "memory_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_id = Column(
        Integer, ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    signal = Column(Text, nullable=False)  # CHECK constraint in migration SQL
    reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"),
    )


class LifecycleLog(Base):
    """Audit log for lifecycle engine phases."""

    __tablename__ = "lifecycle_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phase = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON text
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"),
    )
