"""
M13-C: BenchmarkTask schema validation -- difficulty/task-type
validation, required-context-dimension declarations, architecture
declarations, and evaluation-criteria binding-score validation.
"""

import pytest

from icab.evaluation.grounded import EvaluationReport
from icab.scenarios.models import GroundTruth, ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import KNOWN_SCORE_FIELDS, BenchmarkTask, EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension


def _task(**overrides) -> BenchmarkTask:
    base = dict(
        task_id="t1",
        scenario_id="s1",
        task_type=TaskMode.QA,
        difficulty=ScenarioDifficulty.D1,
        objective="What is x?",
        available_architectures=["historian"],
        required_context_dimensions=[ContextDimension.C5_OPERATIONAL],
        ground_truth=GroundTruth(conclusion="x is normal."),
        evaluation_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
    )
    base.update(overrides)
    return BenchmarkTask(**base)


def test_known_score_fields_are_all_real_evaluation_report_fields():
    """Guards against KNOWN_SCORE_FIELDS drifting from the actual
    evaluator -- if GroundedInvestigationEvaluator ever renames a score,
    this test (not a task author) catches it."""

    for name in KNOWN_SCORE_FIELDS:
        assert name in EvaluationReport.model_fields, f"{name!r} is not a real EvaluationReport field"


def test_minimal_valid_task_constructs():
    task = _task()
    assert task.task_id == "t1"
    assert task.task_type == TaskMode.QA
    assert task.difficulty == ScenarioDifficulty.D1


def test_rejects_unknown_binding_score():
    with pytest.raises(ValueError, match="not_a_real_score"):
        EvaluationCriteria(binding_scores=["not_a_real_score"])


def test_rejects_a_context_dimension_no_available_architecture_supports():
    with pytest.raises(ValueError, match="C3"):
        _task(
            available_architectures=["historian"],
            required_context_dimensions=[ContextDimension.C3_RELATIONAL],
        )


def test_accepts_a_context_dimension_when_a_supporting_architecture_is_present():
    task = _task(
        available_architectures=["historian", "knowledge_graph"],
        required_context_dimensions=[ContextDimension.C3_RELATIONAL],
    )
    assert ContextDimension.C3_RELATIONAL in task.required_context_dimensions


def test_expected_relationships_require_c3_or_c6():
    with pytest.raises(ValueError, match="C3.*C6|C6.*C3"):
        _task(
            available_architectures=["historian"],
            required_context_dimensions=[ContextDimension.C5_OPERATIONAL],
            expected_relationships=[("a", "MONITORS", "b")],
        )


def test_expected_temporal_evidence_requires_c4_or_c7():
    with pytest.raises(ValueError, match="C4.*C7|C7.*C4"):
        _task(
            available_architectures=["historian"],
            required_context_dimensions=[ContextDimension.C5_OPERATIONAL],
            expected_temporal_evidence=True,
        )


def test_expected_temporal_evidence_is_fine_with_c4_declared():
    task = _task(
        available_architectures=["historian"],
        required_context_dimensions=[ContextDimension.C4_TEMPORAL],
        expected_temporal_evidence=True,
    )
    assert task.expected_temporal_evidence is True


def test_expected_relationships_is_fine_with_c6_declared():
    task = _task(
        available_architectures=["knowledge_graph"],
        required_context_dimensions=[ContextDimension.C6_PROCEDURAL],
        expected_relationships=[("a", "CONTROLS", "b")],
    )
    assert task.expected_relationships == [("a", "CONTROLS", "b")]


def test_task_rejects_unknown_fields():
    with pytest.raises(ValueError):
        _task(unexpected="value")


def test_difficulty_must_be_a_locked_value():
    with pytest.raises(ValueError):
        _task(difficulty="D5")


def test_task_type_must_be_a_locked_value():
    with pytest.raises(ValueError):
        _task(task_type="not_a_real_task_type")
