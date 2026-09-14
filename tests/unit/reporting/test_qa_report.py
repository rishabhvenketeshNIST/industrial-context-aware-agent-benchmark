"""
Unit tests for icab.reporting.qa_report -- the researcher-facing
question/answer report. Builds records via the shared factory
(tests/unit/reporting/_factories.py) rather than running anything real;
see tests/integration/test_benchmark_runner_against_real_stack.py for
the end-to-end path producing a real QA report from a real run.
"""

from __future__ import annotations

from icab.agent.interface import EvidenceReference, InvestigationResult, TerminationReason
from icab.agent.llm.agent import LLMInvestigationAgent
from icab.agent.llm.client import LLMResponse, MockLLMClient
from icab.experiments.models import AgentType, ExperimentRunStatus
from icab.reporting.qa_report import (
    build_qa_report,
    build_qa_report_entry,
    render_qa_report_markdown,
)
from icab.scenarios.models import BenchmarkScenario, GroundTruth, ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import BenchmarkTask, EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension

from _factories import make_evaluation, make_record

_GROUND_TRUTH = GroundTruth(
    conclusion="Reactor pressure is near its nominal steady-state value of ~2705 kPa gauge.",
    root_cause_disturbance="idv_06",
    affected_measurements=["urn:icab:measurement:reactor_pressure"],
    affected_equipment=["urn:icab:equipment:reactor"],
    expected_relationships=[("urn:icab:equipment:reactor", "MONITORS", "urn:icab:measurement:reactor_pressure")],
    expected_evidence=["urn:icab:measurement:reactor_pressure"],
)


def _task(**overrides) -> BenchmarkTask:
    base = dict(
        task_id="test-task",
        scenario_id="d1_reactor_pressure_reading",
        task_type=TaskMode.QA,
        difficulty=ScenarioDifficulty.D1,
        objective="What is the current reactor pressure?",
        available_architectures=["historian"],
        required_context_dimensions=[ContextDimension.C5_OPERATIONAL],
        required_evidence=["urn:icab:measurement:reactor_pressure"],
        ground_truth=_GROUND_TRUTH,
        evaluation_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
    )
    base.update(overrides)
    return BenchmarkTask(**base)


def _scenario(**overrides) -> BenchmarkScenario:
    base = dict(
        scenario_id="d1_reactor_pressure_reading",
        name="D1 reactor pressure reading",
        difficulty=ScenarioDifficulty.D1,
        objective="Investigate the reactor's current pressure.",
        seed=101,
        duration_hours=1.0,
        ground_truth=_GROUND_TRUTH,
    )
    base.update(overrides)
    return BenchmarkScenario(**base)


class TestCorrectAnswerRendering:
    def test_renders_readable_prose_not_a_raw_dump(self):
        task = _task()
        record = make_record(
            "run-1",
            task_id=task.task_id,
            task_type=task.task_type.value,
            result=InvestigationResult(
                objective=task.objective,
                conclusion="2712 kPa, normal.",
                evidence=[EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure")],
                termination=TerminationReason.SUBMITTED,
            ),
            evaluation=make_evaluation(task_id=task.task_id, required_evidence_score=1.0),
        )

        entry = build_qa_report_entry(record, task=task)

        assert entry.correct_answer is not None
        assert entry.correct_answer.limitation is None
        assert entry.correct_answer.reference_conclusion == _GROUND_TRUTH.conclusion
        assert entry.correct_answer.root_cause_disturbance == "idv_06"
        assert entry.correct_answer.affected_equipment == ["urn:icab:equipment:reactor"]
        # Relationship triples rendered as readable text, not raw tuples.
        assert entry.correct_answer.expected_relationships == [
            "urn:icab:equipment:reactor --[MONITORS]--> urn:icab:measurement:reactor_pressure"
        ]

        rendered = render_qa_report_markdown(
            build_qa_report(
                [record], benchmark_id="b1", successful_runs=1, failed_runs=0, skipped_runs=0,
                tasks_by_id={task.task_id: task},
            )
        )
        # Never a raw Python/Pydantic repr of GroundTruth.
        assert "GroundTruth(" not in rendered
        assert "root_cause_disturbance=" not in rendered
        # But the readable content is present.
        assert _GROUND_TRUTH.conclusion in rendered
        assert "idv_06" in rendered
        assert "MONITORS" in rendered

    def test_falls_back_to_scenario_ground_truth_when_no_task(self):
        scenario = _scenario()
        record = make_record(
            "run-2",
            result=InvestigationResult(objective=scenario.objective, conclusion="ok", termination=TerminationReason.SUBMITTED),
            evaluation=make_evaluation(),
        )

        entry = build_qa_report_entry(record, task=None, scenario=scenario)

        assert entry.correct_answer.reference_conclusion == _GROUND_TRUTH.conclusion
        assert entry.objective == scenario.objective

    def test_reports_a_limitation_rather_than_fabricating_when_nothing_resolves(self):
        record = make_record("run-3", result=InvestigationResult(objective="?", conclusion="?", termination=TerminationReason.SUBMITTED))

        entry = build_qa_report_entry(record, task=None, scenario=None)

        assert entry.correct_answer.limitation is not None
        assert entry.correct_answer.reference_conclusion == "(unavailable)"
        assert "could be resolved" in entry.correct_answer.limitation


class TestAgentAnswerRendering:
    def test_agent_answer_is_verbatim_not_paraphrased(self):
        task = _task()
        verbatim = "The current reactor pressure is 2712.39 kPa gauge -- within the normal range, per my analysis of X, Y, Z."
        record = make_record(
            "run-4",
            task_id=task.task_id,
            result=InvestigationResult(objective=task.objective, conclusion=verbatim, termination=TerminationReason.SUBMITTED),
            evaluation=make_evaluation(),
        )

        entry = build_qa_report_entry(record, task=task)

        assert entry.agent_answer == verbatim

    def test_failed_run_has_no_agent_answer_and_is_clearly_marked(self):
        task = _task()
        record = make_record(
            "run-5",
            task_id=task.task_id,
            status=ExperimentRunStatus.FAILED,
            error="ConnectError: refused",
            result=None,
            evaluation=None,
        )

        entry = build_qa_report_entry(record, task=task)

        assert entry.agent_answer is None
        assert entry.status == "failed"

        rendered = render_qa_report_markdown(
            build_qa_report([record], benchmark_id="b1", successful_runs=0, failed_runs=1, skipped_runs=0, tasks_by_id={task.task_id: task})
        )
        assert "FAILED" in rendered
        assert "ConnectError" in rendered
        # No fabricated evaluation/metrics for a failed run.
        assert "required_evidence_score | 1.000" not in rendered


class TestRequiredEvidenceAndEvidenceProvided:
    def test_required_evidence_comes_from_the_task_not_invented(self):
        task = _task(required_evidence=["urn:icab:measurement:reactor_pressure", "urn:icab:measurement:reactor_temperature"])
        record = make_record(
            "run-6",
            task_id=task.task_id,
            result=InvestigationResult(
                objective=task.objective,
                conclusion="...",
                evidence=[
                    EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure"),
                ],
                termination=TerminationReason.SUBMITTED,
            ),
            evaluation=make_evaluation(),
        )

        entry = build_qa_report_entry(record, task=task)

        assert entry.required_evidence == [
            "urn:icab:measurement:reactor_pressure",
            "urn:icab:measurement:reactor_temperature",
        ]
        assert entry.evidence_provided == ["get_current_value: urn:icab:measurement:reactor_pressure"]


class TestPerTaskMetrics:
    def test_metrics_are_read_directly_off_the_evaluation_not_recomputed(self):
        task = _task()
        evaluation = make_evaluation(
            required_evidence_score=1.0,
            canonical_id_score=0.9,
            relationship_score=0.5,
            conclusion_correctness_score=1.0,
            grounding_score=1.0,
            completeness_score=0.75,
            tool_call_count=7,
            context_acquired=["a", "b"],
            context_consumed=["a"],
        )
        record = make_record(
            "run-7",
            task_id=task.task_id,
            result=InvestigationResult(objective=task.objective, conclusion="...", termination=TerminationReason.SUBMITTED),
            evaluation=evaluation,
            total_latency_ms=123.4,
            total_tokens=500,
        )

        entry = build_qa_report_entry(record, task=task)

        assert entry.metrics["required_evidence_score"] == 1.0
        assert entry.metrics["canonical_id_score"] == 0.9
        assert entry.metrics["relationship_score"] == 0.5
        assert entry.metrics["conclusion_correctness_score"] == 1.0
        assert entry.metrics["grounding_score"] == 1.0
        assert entry.metrics["completeness_score"] == 0.75
        assert entry.metrics["tool_call_count"] == 7
        assert entry.metrics["context_acquired"] == 2
        assert entry.metrics["context_consumed"] == 1
        assert entry.metrics["latency_ms"] == 123.4
        assert entry.metrics["total_tokens"] == 500

    def test_metrics_are_none_not_zero_when_there_is_no_evaluation(self):
        task = _task()
        record = make_record("run-8", task_id=task.task_id, status=ExperimentRunStatus.FAILED, error="boom", result=None, evaluation=None)

        entry = build_qa_report_entry(record, task=task)

        assert entry.metrics["required_evidence_score"] is None
        assert entry.metrics["tool_call_count"] is None


class TestContextAcquiredVsConsumedAudit:
    """
    Regression coverage for the M13-D follow-up audit: a researcher flagged
    a real D1 run showing `context_acquired=1, context_consumed=0` after a
    single `get_current_value` call whose value the agent's own conclusion
    clearly used, and asked whether that was a bug. Finding: it is CORRECT
    under context_consumed's actual, narrower definition (a discovery id
    exploited by a LATER call -- there is no discovery step here at all),
    and grounding_score/required_evidence_score already answer "was the
    acquired value actually used" -- see
    docs/architecture/llm-agent.md#context_acquired-vs-context_consumed.
    These tests reproduce that exact, real scenario and lock in that the
    report renders it accurately AND explains it, rather than leaving a
    reader to conclude the agent ignored its own evidence.
    """

    def test_reproduces_the_exact_reported_scenario_and_is_self_consistent(self):
        task = _task()
        evaluation = make_evaluation(
            required_evidence_score=1.0,
            canonical_id_score=1.0,
            grounding_score=1.0,
            context_acquired=["urn:icab:measurement:reactor_pressure"],
            context_consumed=[],  # no discovery step preceded the single call
            tool_call_count=1,
        )
        record = make_record(
            "run-audit-1",
            task_id=task.task_id,
            result=InvestigationResult(
                objective=task.objective,
                conclusion=(
                    "The current reactor pressure is 2712.39 kPa gauge, which is below the "
                    "3000 kPa high-pressure trip threshold and therefore within the normal "
                    "safe operating range."
                ),
                evidence=[EvidenceReference(source="get_current_value", identifier="urn:icab:measurement:reactor_pressure")],
                termination=TerminationReason.SUBMITTED,
            ),
            evaluation=evaluation,
        )

        entry = build_qa_report_entry(record, task=task)

        # The reported numbers, reproduced exactly.
        assert entry.metrics["context_acquired"] == 1
        assert entry.metrics["context_consumed"] == 0
        assert entry.metrics["tool_call_count"] == 1
        # Not a contradiction: the SAME run's own evidence/grounding
        # metrics confirm the acquired value WAS used correctly.
        assert entry.metrics["required_evidence_score"] == 1.0
        assert entry.metrics["grounding_score"] == 1.0
        assert entry.evidence_provided == ["get_current_value: urn:icab:measurement:reactor_pressure"]

    def test_report_explains_context_consumed_is_not_usage(self):
        report = build_qa_report(
            [
                make_record(
                    "run-audit-2",
                    result=InvestigationResult(objective="q", conclusion="a", termination=TerminationReason.SUBMITTED),
                    evaluation=make_evaluation(context_acquired=["x"], context_consumed=[]),
                )
            ],
            benchmark_id="audit",
            successful_runs=1,
            failed_runs=0,
            skipped_runs=0,
        )

        rendered = render_qa_report_markdown(report)

        # A top-of-report glossary explains the distinction once...
        assert "discovery" in rendered.lower()
        assert "not" in rendered.lower() and "used" in rendered.lower()
        assert "required_evidence_score" in rendered
        # ...and the per-run metrics table itself carries a clarifying
        # note directly on the context_consumed row, not just at the top.
        assert "context_consumed _(" in rendered
        assert "context_acquired _(" in rendered


class TestOverallSummary:
    def test_counts_and_breakdowns_reflect_the_records_passed_in(self):
        task = _task()
        completed = make_record(
            "run-9",
            task_id=task.task_id,
            task_type=task.task_type.value,
            result=InvestigationResult(objective=task.objective, conclusion="ok", termination=TerminationReason.SUBMITTED),
            evaluation=make_evaluation(required_evidence_score=1.0),
        )
        failed = make_record("run-10", task_id=task.task_id, status=ExperimentRunStatus.FAILED, error="boom")

        report = build_qa_report(
            [completed, failed],
            benchmark_id="b2",
            successful_runs=1,
            failed_runs=1,
            skipped_runs=2,
            tasks_by_id={task.task_id: task},
        )

        assert report.total_runs == 4  # 1 successful + 1 failed + 2 skipped
        assert report.successful_runs == 1
        assert report.failed_runs == 1
        assert report.skipped_runs == 2
        assert len(report.entries) == 2  # skipped runs never produced a record to list

        assert report.by_architecture is not None
        assert report.by_difficulty is not None
        assert report.by_task_type is not None

        rendered = render_qa_report_markdown(report)
        assert "**Total runs:** 4" in rendered
        assert "**Successful:** 1" in rendered
        assert "**Failed:** 1" in rendered
        assert "**Skipped:** 2" in rendered

    def test_empty_records_produce_a_report_with_no_aggregate_breakdowns(self):
        report = build_qa_report([], benchmark_id="b3", successful_runs=0, failed_runs=0, skipped_runs=1)

        assert report.entries == []
        assert report.overall is None
        assert report.by_architecture is None


class TestGroundTruthNeverReachesTheAgent:
    """
    The core M13-D security invariant, verified end to end: the exact
    ground truth text/ids this report displays must never appear in the
    messages actually sent to the LLM during the run that produced it.
    """

    def test_llm_messages_never_contain_what_the_qa_report_later_reveals(self):
        task = _task()

        llm = MockLLMClient(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(),
                ),
            ]
        )

        class _StubGatewayClient:
            trace_collector = None

        agent = LLMInvestigationAgent(_StubGatewayClient(), llm, max_steps=1)
        result = agent.run(
            objective=task.objective,
            initial_state={"scenario_id": task.scenario_id, "difficulty": task.difficulty.value},
        )

        sent_messages = str(llm.calls[0]["messages"])

        # Nothing the QA report is about to reveal was ever sent to the LLM.
        assert task.ground_truth.root_cause_disturbance not in sent_messages
        assert task.ground_truth.conclusion not in sent_messages
        for measurement in task.ground_truth.affected_measurements:
            assert measurement not in sent_messages
        for equipment in task.ground_truth.affected_equipment:
            assert equipment not in sent_messages

        # Now build the report from the (fabricated-for-this-test) result
        # and confirm the report DOES surface it -- proving this is a
        # genuine boundary (report sees more than the agent did), not
        # merely "both happen to lack it."
        record = make_record(
            "run-security",
            task_id=task.task_id,
            result=result,
            evaluation=make_evaluation(),
        )
        rendered = render_qa_report_markdown(
            build_qa_report(
                [record], benchmark_id="b-security", successful_runs=1, failed_runs=0, skipped_runs=0,
                tasks_by_id={task.task_id: task},
            )
        )

        assert task.ground_truth.root_cause_disturbance in rendered
        assert task.ground_truth.conclusion in rendered

    def test_building_the_report_makes_no_agent_gateway_or_llm_call(self, monkeypatch):
        """
        `build_qa_report`/`render_qa_report_markdown` operate purely on
        already-persisted records -- guard against a future change
        accidentally adding a network call by making httpx.post/get raise
        if either is invoked during report construction.
        """

        import httpx

        def _forbidden(*args, **kwargs):
            raise AssertionError("qa_report must not make any network call")

        monkeypatch.setattr(httpx, "post", _forbidden)
        monkeypatch.setattr(httpx, "get", _forbidden)

        task = _task()
        record = make_record(
            "run-11",
            task_id=task.task_id,
            result=InvestigationResult(objective=task.objective, conclusion="ok", termination=TerminationReason.SUBMITTED),
            evaluation=make_evaluation(),
        )

        report = build_qa_report(
            [record], benchmark_id="b4", successful_runs=1, failed_runs=0, skipped_runs=0, tasks_by_id={task.task_id: task}
        )
        render_qa_report_markdown(report)  # must not raise
