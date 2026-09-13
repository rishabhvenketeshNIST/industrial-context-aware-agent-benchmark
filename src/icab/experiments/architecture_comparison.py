from dataclasses import dataclass
from typing import Any

from icab.agent.architecture_aware import ArchitectureAwareAgent
from icab.agent.client import AgentGatewayClient
from icab.evaluation.cases import InvestigationCase
from icab.evaluation.investigation import InvestigationEvaluator
from icab.trace.collector import TraceCollector


@dataclass(frozen=True)
class ArchitectureComparisonResult:
    """Comparable result for one architecture/case execution."""

    architecture: str
    case_id: str
    objective_match: bool
    evidence_score: float
    normalized_context_score: float
    tool_calls: int
    context_acquired: tuple[str, ...]
    context_consumed: tuple[str, ...]


class ArchitectureComparisonRunner:
    """Run the same investigation case across multiple architectures."""

    def __init__(
        self,
        clients: dict[str, AgentGatewayClient],
        *,
        evaluator: InvestigationEvaluator | None = None,
    ) -> None:
        self.clients = clients
        self.evaluator = evaluator or InvestigationEvaluator()

    def run(
        self,
        case: InvestigationCase,
        *,
        initial_state: dict[str, Any] | None = None,
    ) -> list[ArchitectureComparisonResult]:
        initial_state = initial_state or {}

        results = []

        for architecture, client in self.clients.items():
            trace_collector = TraceCollector()
            client.trace_collector = trace_collector

            agent = ArchitectureAwareAgent(
                client,
                architecture=architecture,
            )

            result = agent.run(
                objective=case.objective,
                initial_state=initial_state,
            )

            score = self.evaluator.evaluate(case, result)
            events = trace_collector.events()

            results.append(
                ArchitectureComparisonResult(
                    architecture=architecture,
                    case_id=case.case_id,
                    objective_match=score["objective_match"],
                    evidence_score=score["evidence_score"],
                    normalized_context_score=score[
                        "normalized_context_score"
                    ],
                    tool_calls=len(events),
                    context_acquired=tuple(
                        sorted(
                            {
                                item
                                for event in events
                                for item in event.context_acquired
                            }
                        )
                    ),
                    context_consumed=tuple(
                        sorted(
                            {
                                item
                                for event in events
                                for item in event.context_consumed
                            }
                        )
                    ),
                )
            )

        return results