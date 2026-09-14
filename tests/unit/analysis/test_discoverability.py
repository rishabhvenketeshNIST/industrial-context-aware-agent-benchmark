"""Unit tests for `icab.analysis.discoverability` -- the 5-stage discoverability pipeline (ICAB v2 Phase 12)."""

from __future__ import annotations

from icab.analysis import DiscoverabilityStage, classify_discoverability, discoverability_breakdown
from icab.experiments.models import ExperimentRunStatus

from _v2_factories import make_evaluation, make_v2_record


class TestStageClassification:
    def test_infrastructure_failure_is_not_reached(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            status=ExperimentRunStatus.FAILED, error="ConnectError: [WinError 10061] connection refused",
        )

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.NOT_REACHED
        assert "infrastructure-shaped" in classification.reason

    def test_no_context_acquired_stops_at_exists_in_architecture(self):
        record = make_v2_record(
            "r1", context_combination_id="C3", architectures=["knowledge_graph"],
            evaluation=make_evaluation(context_acquired=[], required_evidence_score=0.0),
        )

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.EXISTS_IN_ARCHITECTURE

    def test_partial_required_evidence_stops_at_discovered_identifier(self):
        record = make_v2_record(
            "r1", context_combination_id="C3", architectures=["knowledge_graph"],
            evaluation=make_evaluation(context_acquired=["urn:icab:equipment:reactor"], required_evidence_score=0.5),
        )

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.DISCOVERED_IDENTIFIER

    def test_invalid_canonical_id_stops_at_retrieved_value(self):
        record = make_v2_record(
            "r1", context_combination_id="C3", architectures=["knowledge_graph"],
            evaluation=make_evaluation(required_evidence_score=1.0, canonical_id_score=0.5),
        )

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.RETRIEVED_VALUE

    def test_unsupported_numeric_claim_stops_at_used_as_evidence(self):
        record = make_v2_record(
            "r1", context_combination_id="C5", architectures=["historian"],
            evaluation=make_evaluation(required_evidence_score=1.0, canonical_id_score=1.0, grounding_score=0.0),
        )

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.USED_AS_EVIDENCE

    def test_full_success_reaches_grounded_in_conclusion(self):
        record = make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation())

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.GROUNDED_IN_CONCLUSION

    def test_a_real_area_knowledge_graph_discoverability_failure_is_never_mistaken_for_a_reasoning_failure(self):
        """
        Mirrors the real v2-area-smoke finding (docs/research/development-
        history.md): a knowledge_graph-only Area task where the agent could
        not discover the Area's own canonical id from a plain-language
        objective -- this must classify as an early-pipeline discovery
        problem, never as if the agent reasoned poorly over evidence it
        never had.
        """

        record = make_v2_record(
            "r1", use_case_id="area-process-cell-composition", isa95_level="area",
            context_combination_id="C2+C3", architectures=["knowledge_graph"],
            evaluation=make_evaluation(context_acquired=[], required_evidence_score=0.0, conclusion_correctness_score=0.0),
        )

        classification = classify_discoverability([record])[0]

        assert classification.stage_reached == DiscoverabilityStage.EXISTS_IN_ARCHITECTURE
        assert classification.stage_reached != DiscoverabilityStage.GROUNDED_IN_CONCLUSION


class TestDiscoverabilityBreakdown:
    def test_counts_every_stage_including_zero(self):
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation()),
            make_v2_record(
                "r2", context_combination_id="C3", architectures=["knowledge_graph"],
                evaluation=make_evaluation(context_acquired=[], required_evidence_score=0.0),
            ),
        ]

        breakdown = discoverability_breakdown(records)

        assert breakdown[DiscoverabilityStage.GROUNDED_IN_CONCLUSION.value] == 1
        assert breakdown[DiscoverabilityStage.EXISTS_IN_ARCHITECTURE.value] == 1
        assert breakdown[DiscoverabilityStage.NOT_REACHED.value] == 0  # present, at zero
        assert sum(breakdown.values()) == 2
