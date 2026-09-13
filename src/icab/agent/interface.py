from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TerminationReason(StrEnum):
    """How an investigation ended (used by evaluation for completeness scoring)."""

    SUBMITTED = "submitted"
    NO_TOOL_CALL = "no_tool_call"
    STEP_BUDGET_EXCEEDED = "step_budget_exceeded"


class EvidenceReference(BaseModel):
    """Reference to information used to support an investigation."""

    model_config = ConfigDict(extra="forbid")

    source: str
    identifier: str

class NormalizedContext(BaseModel):
    """Architecture-independent context acquired during an investigation."""

    model_config = ConfigDict(extra="forbid")

    assets: list[dict[str, Any]] = Field(default_factory=list)
    measurements: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[EvidenceReference] = Field(default_factory=list)

class InvestigationResult(BaseModel):
    """Standard result returned by an ICAB investigation agent."""

    model_config = ConfigDict(extra="forbid")

    objective: str
    conclusion: str
    findings: dict[str, Any] = Field(default_factory=dict)
    context: NormalizedContext = Field(default_factory=NormalizedContext)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    termination: TerminationReason = Field(
        default=TerminationReason.SUBMITTED,
        description=(
            "How the investigation ended. Deterministic baseline agents "
            "always complete their fixed sequence and use the default; "
            "LLMInvestigationAgent sets this explicitly."
        ),
    )


class Agent(ABC):
    """Interface implemented by an ICAB benchmark agent."""

    @abstractmethod
    def run(
        self,
        *,
        objective: str,
        initial_state: dict[str, Any],
    ) -> InvestigationResult:
        """Run an investigation and return the final result."""
        raise NotImplementedError
