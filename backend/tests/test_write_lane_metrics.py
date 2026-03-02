import asyncio

import pytest

from runtime_state import WriteLaneCoordinator


@pytest.mark.asyncio
async def test_write_lane_status_includes_new_metrics_fields_with_defaults() -> None:
    coordinator = WriteLaneCoordinator()

    status = await coordinator.status()

    assert status["global_concurrency"] >= 1
    assert status["global_active"] == 0
    assert status["global_waiting"] == 0
    assert status["session_waiting_count"] == 0
    assert status["session_waiting_sessions"] == 0
    assert status["max_session_waiting"] == 0
    assert status["wait_warn_ms"] >= 1
    assert status["writes_total"] == 0
    assert status["writes_failed"] == 0
    assert status["writes_success"] == 0
    assert status["failure_rate"] == 0.0
    assert status["session_wait_ms_p95"] == 0
    assert status["global_wait_ms_p95"] == 0
    assert status["duration_ms_p95"] == 0
    assert status["last_error"] is None


@pytest.mark.asyncio
async def test_write_lane_metrics_track_outcomes_and_latency_percentiles() -> None:
    coordinator = WriteLaneCoordinator()

    async def _hold(started: asyncio.Event) -> str:
        started.set()
        await asyncio.sleep(0.03)
        return "hold_done"

    async def _ok(value: str) -> str:
        return value

    global_started = asyncio.Event()
    global_first = asyncio.create_task(
        coordinator.run_write(
            session_id="global-first",
            operation="create_memory",
            task=lambda: _hold(global_started),
        )
    )
    await global_started.wait()
    global_second = await coordinator.run_write(
        session_id="global-second",
        operation="create_memory",
        task=lambda: _ok("global_waited"),
    )
    assert global_second == "global_waited"
    assert await global_first == "hold_done"

    session_started = asyncio.Event()
    session_first = asyncio.create_task(
        coordinator.run_write(
            session_id="shared-session",
            operation="update_memory",
            task=lambda: _hold(session_started),
        )
    )
    await session_started.wait()
    session_second = await coordinator.run_write(
        session_id="shared-session",
        operation="update_memory",
        task=lambda: _ok("session_waited"),
    )
    assert session_second == "session_waited"
    assert await session_first == "hold_done"

    async def _fail() -> str:
        raise RuntimeError("write_failed_for_test")

    with pytest.raises(RuntimeError, match="write_failed_for_test"):
        await coordinator.run_write(
            session_id="failure-session",
            operation="delete_memory",
            task=_fail,
        )

    status = await coordinator.status()

    assert status["writes_total"] == 5
    assert status["writes_success"] == 4
    assert status["writes_failed"] == 1
    assert status["failure_rate"] == pytest.approx(0.2)
    assert status["session_wait_ms_p95"] > 0
    assert status["global_wait_ms_p95"] > 0
    assert status["duration_ms_p95"] > 0
    assert status["last_error"] == "write_failed_for_test"
