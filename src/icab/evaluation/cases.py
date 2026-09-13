from dataclasses import dataclass


@dataclass(frozen=True)
class InvestigationCase:
    case_id: str
    objective: str
    expected_architecture: str
    required_evidence: tuple[str, ...]


PROTOTYPE_REACTOR_CASE = InvestigationCase(
    case_id="reactor_context_001",
    objective="Investigate the reactor and identify the available process measurements.",
    expected_architecture="architecture_under_test",
    required_evidence=(
        "reactor",
        "pressure",
        "temperature",
        "level",
    ),
)
