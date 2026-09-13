from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceEvent(BaseModel):
    """A single recorded agent-environment interaction."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    step: int = Field(ge=0)

    action: str
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None

    latency_ms: float | None = Field(default=None, ge=0)
    token_usage: dict[str, int] | None = None

    context_acquired: list[str] = Field(default_factory=list)
    context_consumed: list[str] = Field(default_factory=list)


class InvestigationTrace(BaseModel):
    """Trace for one complete ICAB investigation run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    objective: str
    agent: str

    started_at: datetime
    completed_at: datetime | None = None

    status: str = "running"

    events: list[TraceEvent] = Field(default_factory=list)

    context_acquired: list[str] = Field(default_factory=list)
    context_consumed: list[str] = Field(default_factory=list)
