"""
Unit tests for `icab.export.build.build_canonical_record` -- exercises a
REAL Equipment question/task (no hand-authored fixture question) so the
schema mapping is checked against genuine ICAB data, with an
ExperimentRecord/trace built by the test's own factories (no gateway/
agent/LLM call).
"""

from __future__ import annotations

import json

from icab.evaluation.grounded import EvaluationReport
from icab.experiments.models import ExperimentRunStatus
from icab.export.build import build_canonical_record
from icab.questions import QuestionBankRegistry
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.isa95 import ISA95Level
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

from _export_factories import make_evaluation, make_record, make_trace

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"
QUESTIONS_DIR = "configs/questions/equipment"

QUESTION_ID = "Q-d1-qa-current-pressure"
TASK_ID = "d1-qa-current-pressure"


def _real_question_and_task():
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(QUESTIONS_DIR, use_case_registry=use_case_registry, task_registry=task_registry)
    question = question_registry.get(QUESTION_ID)
    task = task_registry.get(TASK_ID)
    return question, task


class TestBuildCanonicalRecord:
    def test_maps_question_and_ground_truth_from_real_icab_data(self):
        question, task = _real_question_and_task()
        record = make_record("run-1", evaluation=make_evaluation())
        trace = make_trace()

        canonical = build_canonical_record(
            record, trace, question=question, task=task, campaign_id="campaign-1", benchmark_name="icab-equipment-v1", benchmark_version="1.0.0"
        )

        assert canonical.execution_id == "run-1"
        assert canonical.question.id == QUESTION_ID
        assert canonical.question.text == question.question_text
        assert canonical.question.use_case == question.use_case_id
        assert canonical.question.category == question.tags[0].value
        assert canonical.ground_truth.answer == task.ground_truth.conclusion
        assert canonical.ground_truth.affected_equipment == task.ground_truth.affected_equipment
        assert canonical.ground_truth.expected_evidence == task.ground_truth.expected_evidence
        assert canonical.ground_truth.unit is None
        assert canonical.ground_truth.acceptable_range is None

    def test_llm_answer_is_the_result_conclusion_verbatim(self):
        question, task = _real_question_and_task()
        record = make_record("run-2", evaluation=make_evaluation())
        canonical = build_canonical_record(record, make_trace(), question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version=None)

        assert canonical.llm.answer == record.result.conclusion
        assert canonical.llm.raw_response is None  # never fabricated -- ICAB does not persist it

    def test_evaluation_correct_applies_the_tasks_own_binding_criteria(self):
        question, task = _real_question_and_task()
        # binding_scores=[required_evidence_score, grounding_score], threshold=1.0
        passing_eval = make_evaluation(required_evidence_score=1.0, grounding_score=1.0)
        record = make_record("run-3", evaluation=passing_eval)
        canonical = build_canonical_record(record, make_trace(), question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version=None)
        assert canonical.evaluation.correct is True

        failing_eval = make_evaluation(required_evidence_score=0.0, grounding_score=1.0)
        record2 = make_record("run-4", evaluation=failing_eval)
        canonical2 = build_canonical_record(record2, make_trace(), question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version=None)
        assert canonical2.evaluation.correct is False

    def test_correct_is_null_not_guessed_when_there_is_no_evaluation(self):
        question, task = _real_question_and_task()
        record = make_record("run-5", evaluation=None, status=ExperimentRunStatus.FAILED, result=None, error="boom")
        canonical = build_canonical_record(record, [], question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version=None)

        assert canonical.evaluation.correct is None
        assert canonical.execution.success is False
        assert canonical.trace.errors == ["boom"]

    def test_ground_truth_is_null_with_a_limitation_when_no_task_or_question_resolves(self):
        record = make_record("run-6", evaluation=make_evaluation())
        canonical = build_canonical_record(record, make_trace(), question=None, task=None, campaign_id="c", benchmark_name="b", benchmark_version=None)

        assert canonical.ground_truth.answer is None
        assert canonical.ground_truth.limitation is not None
        assert canonical.question.id == "Q-d1-qa-current-pressure"  # falls back to config.question_id

    def test_context_dimensions_are_never_invented(self):
        question, task = _real_question_and_task()
        record = make_record("run-7", evaluation=make_evaluation())
        canonical = build_canonical_record(record, make_trace(), question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version=None)

        assert canonical.context.hypothesized_required_dimensions == [d.value for d in question.hypothesized_required_context]
        assert canonical.context.context_acquired == list(record.evaluation.context_acquired)
        assert canonical.context.context_consumed == list(record.evaluation.context_consumed)

    def test_the_full_record_round_trips_through_plain_json_with_no_icab_import(self):
        question, task = _real_question_and_task()
        record = make_record("run-8", evaluation=make_evaluation())
        canonical = build_canonical_record(record, make_trace(), question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version="1.0.0")

        dumped = canonical.model_dump(mode="json")
        reparsed = json.loads(json.dumps(dumped))  # plain json.dumps/loads -- no pydantic/ICAB involved
        assert reparsed["execution_id"] == "run-8"
        assert reparsed["trace"]["tool_calls"][0]["tool"] == "get_measurement"

    def test_trace_result_containing_non_json_native_values_is_sanitized_not_dropped(self):
        from datetime import UTC, datetime as dt

        question, task = _real_question_and_task()
        record = make_record("run-9", evaluation=make_evaluation())
        weird_trace = make_trace(result={"observed_at": dt(2026, 9, 14, tzinfo=UTC)})

        canonical = build_canonical_record(record, weird_trace, question=question, task=task, campaign_id="c", benchmark_name="b", benchmark_version=None)

        json.dumps(canonical.model_dump(mode="json"))  # must not raise
        assert "2026-09-14" in canonical.trace.tool_calls[0]["result"]["observed_at"]
