from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
