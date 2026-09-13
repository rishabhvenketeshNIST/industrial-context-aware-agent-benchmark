from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvestigationTask(BaseModel):
    """A task presented to an ICAB investigation agent."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    initial_state: dict[str, Any] = Field(default_factory=dict)
