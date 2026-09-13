from datetime import datetime
from typing import Any

from .models import TraceEvent


class TraceCollector:
    """Collect trace events for a single benchmark execution."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(
        self,
        *,
        step: int,
        action: str,
        tool: str | None = None,
        arguments: dict[str, Any] | None = None,
        result: Any = None,
        latency_ms: float | None = None,
        token_usage: dict[str, int] | None = None,
        timestamp: datetime | None = None,
        context_acquired: list[str] | None = None,
        context_consumed: list[str] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            timestamp=timestamp or datetime.now().astimezone(),
            step=step,
            action=action,
            tool=tool,
            arguments=arguments or {},
            result=result,
            latency_ms=latency_ms,
            token_usage=token_usage,
            context_acquired=context_acquired or [],
            context_consumed=context_consumed or [],
        )

        self._events.append(event)
        return event

    def events(self) -> list[TraceEvent]:
        """Return the collected events in execution order."""
        return list(self._events)

    def clear(self) -> None:
        """Clear all collected events."""
        self._events.clear()
