from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException

from runtime_state import runtime_state


async def run_write_lane(
    operation: str,
    task: Callable[[], Awaitable[Any]],
    *,
    enabled: bool = True,
    session_id: Optional[str] = None,
    default_session_id: Optional[str] = None,
    operation_prefix: str = "",
) -> Any:
    if not enabled:
        return await task()

    resolved_session_id = str(session_id or "").strip() or default_session_id
    resolved_operation = (
        f"{operation_prefix}{operation}" if operation_prefix else operation
    )
    try:
        return await runtime_state.write_lanes.run_write(
            session_id=resolved_session_id,
            operation=resolved_operation,
            task=task,
        )
    except RuntimeError as exc:
        if str(exc) == "write_lane_timeout":
            raise HTTPException(
                status_code=503,
                detail={"error": "write_lane_timeout"},
            ) from exc
        raise
