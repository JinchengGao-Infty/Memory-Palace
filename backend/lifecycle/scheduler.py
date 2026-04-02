"""
Lifecycle Scheduler — cron-scheduled lifecycle engine runner.

Runs the full lifecycle engine (phases 1-6) on a configurable interval.
Default: every 6 hours ("0 */6 * * *").

Follows the VitalityDecayCoordinator pattern from runtime_state.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from shared_utils import env_bool as _env_bool

logger = logging.getLogger(__name__)


def _parse_interval_hours(cron_expr: str) -> float:
    """Extract interval hours from simple cron expressions.

    Supports:
      - "0 */N * * *" → every N hours
      - "*/N * * * *" → every N minutes (converted to hours)
      - fallback → 6 hours
    """
    cron_expr = cron_expr.strip()

    # Match "0 */N * * *" (every N hours)
    m = re.match(r"^0\s+\*/(\d+)\s+\*\s+\*\s+\*$", cron_expr)
    if m:
        return max(0.1, float(m.group(1)))

    # Match "*/N * * * *" (every N minutes)
    m = re.match(r"^\*/(\d+)\s+\*\s+\*\s+\*\s+\*$", cron_expr)
    if m:
        return max(0.01, float(m.group(1)) / 60.0)

    return 6.0


class LifecycleScheduler:
    """Cron-scheduled lifecycle engine runner."""

    def __init__(self) -> None:
        self._enabled = _env_bool("LIFECYCLE_ENABLED", True)
        self._cron_expression = os.environ.get(
            "LIFECYCLE_CRON_EXPRESSION", "0 */6 * * *"
        )
        self._interval_hours = _parse_interval_hours(self._cron_expression)
        self._guard = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._client_factory: Optional[Callable[[], Any]] = None
        self._last_result: Dict[str, Any] = {"status": "not_started"}
        self._started = False

    def set_client_factory(self, factory: Callable[[], Any]) -> None:
        """Set the SQLiteClient factory for creating engine instances."""
        if self._client_factory is not None:
            return
        self._client_factory = factory

    async def start(self) -> None:
        """Start the cron scheduler as a background asyncio task."""
        if self._started:
            return
        self._started = True
        if not self._enabled:
            logger.info("Lifecycle scheduler disabled (LIFECYCLE_ENABLED=false)")
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="lifecycle-scheduler")
        logger.info(
            "Lifecycle scheduler started (interval=%.1fh, cron=%s)",
            self._interval_hours,
            self._cron_expression,
        )

    async def _run_loop(self) -> None:
        """Sleep-based loop that runs lifecycle engine at the configured interval."""
        interval_seconds = self._interval_hours * 3600
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    await self._execute()
                except Exception:
                    logger.exception("Lifecycle scheduler run failed")
        except asyncio.CancelledError:
            logger.info("Lifecycle scheduler loop cancelled")

    async def _execute(self) -> Dict[str, Any]:
        """Run the lifecycle engine once under the guard lock."""
        async with self._guard:
            if self._client_factory is None:
                self._last_result = {
                    "status": "error",
                    "reason": "client_factory_not_set",
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                return dict(self._last_result)

            try:
                from lifecycle.engine import LifecycleEngine

                client = self._client_factory()
                engine = LifecycleEngine(client)
                started = time.monotonic()
                phases = await engine.run()
                elapsed = time.monotonic() - started

                self._last_result = {
                    "status": "completed",
                    "phases": phases,
                    "elapsed_seconds": round(elapsed, 3),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                logger.info(
                    "Lifecycle run completed in %.2fs", elapsed
                )
            except Exception as exc:
                self._last_result = {
                    "status": "error",
                    "reason": str(exc),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                logger.exception("Lifecycle engine execution failed")

            return dict(self._last_result)

    async def trigger(self) -> Dict[str, Any]:
        """Manual trigger. Waits for any in-progress run to finish."""
        return await self._execute()

    async def stop(self) -> None:
        """Cancel the background task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def status(self) -> Dict[str, Any]:
        """Return last run info and scheduler configuration."""
        return {
            "enabled": self._enabled,
            "cron_expression": self._cron_expression,
            "interval_hours": self._interval_hours,
            "running": self._task is not None and not self._task.done(),
            **dict(self._last_result),
        }
