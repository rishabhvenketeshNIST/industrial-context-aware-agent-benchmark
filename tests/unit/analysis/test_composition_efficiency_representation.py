"""ICAB-CC/ICAB-CE/ICAB-CR unit tests: composition, efficiency, and representation analysis."""

from __future__ import annotations

from icab.analysis import analyze_context_composition, analyze_context_efficiency, analyze_representation
from icab.analysis.representation import ARCHITECTURE_REPRESENTATION_LABELS
from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension
from icab.usecases import ISA95Level, IndustrialUseCase

from _v2_factories import make_evaluation, make_v2_record


def _use_case() -> IndustrialUseCase:
    return IndustrialUseCase(
        use_case_id="eq-value-and-relationship-combination",
        name="Combine value and relationship",
        description="Test use case.",
        isa95_level=ISA95Level.EQUIPMENT,
        task_type=TaskMode.INVESTIGATION,
        required_context=[ContextDimension.C5_OPERATIONAL, ContextDimension.C3_RELATIONAL],
        candidate_context=[ContextDimension.C5_OPERATIONAL, ContextDimension.C3_RELATIONAL],
        success_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
        applicable_scenarios=["d2_reactor_context_combination"],
        difficulty=ScenarioDifficulty.D2,
    )


class TestAnalyzeContextComposition:
    def test_reports_one_finding_per_tested_combination(self):
        use_case = _use_case()
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation(conclusion_correctness_score=0.5)),
            make_v2_record("r2", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], evaluation=make_evaluation(conclusion_correctness_score=1.0)),
        ]

        report = analyze_context_composition(records, use_case)

        assert {f.context_combination_id for f in report.findings} == {"C5", "C3+C5"}
        assert report.best_tested_combination == "C3+C5"

    def test_empty_records_yields_no_findings_and_no_best(self):
        report = analyze_context_composition([], _use_case())
        assert report.findings == []
        assert report.best_tested_combination is None


class TestAnalyzeContextEfficiency:
    def test_groups_by_combination_and_architecture_by_default(self):
        use_case = _use_case()
        records = [
            make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation(tool_call_count=3)),
            make_v2_record("r2", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], evaluation=make_evaluation(tool_call_count=7)),
        ]

        report = analyze_context_efficiency(records, use_case)

        assert len(report.groups) == 2
        tool_calls = {tuple(sorted(g["group_key"].items())): g["metrics"]["tool_call_count"] for g in report.groups}
        assert any(v == 3.0 for v in tool_calls.values())
        assert any(v == 7.0 for v in tool_calls.values())

    def test_computes_no_new_metric_names(self):
        from icab.reporting.metrics import EFFICIENCY_METRICS

        use_case = _use_case()
        record = make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation())
        report = analyze_context_efficiency([record], use_case)

        expected_names = {name for name, _label in EFFICIENCY_METRICS}
        for group in report.groups:
            assert set(group["metrics"]) == expected_names


class TestAnalyzeRepresentation:
    def test_only_single_architecture_runs_are_compared(self):
        use_case = _use_case()
        single = make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation())
        multi = make_v2_record("r2", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], evaluation=make_evaluation())

        report = analyze_representation([single, multi], use_case)

        assert {f.architecture for f in report.findings} == {"historian"}

    def test_each_finding_carries_its_real_documented_representation_label(self):
        use_case = _use_case()
        record = make_v2_record("r1", context_combination_id="C5", architectures=["historian"], evaluation=make_evaluation())

        report = analyze_representation([record], use_case)

        assert report.findings[0].representation == ARCHITECTURE_REPRESENTATION_LABELS["historian"]

    def test_no_single_architecture_runs_yields_empty_findings(self):
        use_case = _use_case()
        multi = make_v2_record("r1", context_combination_id="C3+C5", architectures=["historian", "knowledge_graph"], evaluation=make_evaluation())

        report = analyze_representation([multi], use_case)

        assert report.findings == []
