from typing import Any

from icab.agent.interface import InvestigationResult
from icab.evaluation.cases import InvestigationCase


class InvestigationEvaluator:
    def evaluate(
        self,
        case: InvestigationCase,
        result: InvestigationResult,
    ) -> dict[str, Any]:
        text = self._collect_text(result)

        evidence_hits = {
            item: item.lower() in text.lower()
            for item in case.required_evidence
        }

        normalized_hits = self._evaluate_normalized_context(
            case,
            result,
        )

        return {
            "case_id": case.case_id,
            "objective_match": result.objective == case.objective,
            "evidence_hits": evidence_hits,
            "evidence_score": sum(evidence_hits.values()) / len(evidence_hits),
            "normalized_context_hits": normalized_hits,
            "normalized_context_score": (
                sum(normalized_hits.values()) / len(normalized_hits)
                if normalized_hits
                else 0.0
            ),
            "complete": all(evidence_hits.values()),
        }

    @staticmethod
    def _evaluate_normalized_context(
        case: InvestigationCase,
        result: InvestigationResult,
    ) -> dict[str, bool]:
        context = result.context

        asset_text = " ".join(
            str(asset.get("name", ""))
            for asset in context.assets
        ).lower()

        measurement_text = " ".join(
            str(measurement.get("name", ""))
            for measurement in context.measurements
        ).lower()

        relationship_text = " ".join(
            str(relationship.get("predicate", ""))
            for relationship in context.relationships
        ).lower()

        context_text = (
            f"{asset_text} {measurement_text} {relationship_text}"
        )

        return {
            item: item.lower() in context_text
            for item in case.required_evidence
        }

    @staticmethod
    def _collect_text(result: InvestigationResult) -> str:
        return "\n".join(
            [
                result.objective,
                result.conclusion,
                str(result.findings),
                str(result.evidence),
            ]
        )