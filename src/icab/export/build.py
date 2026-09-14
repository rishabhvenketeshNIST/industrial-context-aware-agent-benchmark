"""
Transforms one already-persisted `ExperimentRecord` (+ its trace, the
`Question` it answers, and the `BenchmarkTask` that concretely realized
it) into one standalone `CanonicalExecutionRecord`.

Makes NO gateway/agent/LLM call and computes NO new score: ground truth
and per-run metrics are read via the existing, reused
`icab.reporting.qa_report.build_qa_report_entry` (the same function the
M13-D QA report already uses), and failure classification via the
existing `icab.analysis.failure_taxonomy.classify_failures` -- this
module only RESHAPES already-computed data into the export schema.
"""

from __future__ import annotations

import json
from typing import Any

from icab.analysis.failure_taxonomy import FailureCategory, classify_failures
from icab.experiments.models import ExperimentRecord, ExperimentRunStatus
from icab.questions.models import Question
from icab.reporting.qa_report import build_qa_report_entry
from icab.tasks.benchmark_task import BenchmarkTask
from icab.tasks.context_dimensions import provided_dimensions
from icab.trace.models import TraceEvent

from .schema import (
    BenchmarkInfo,
    CanonicalExecutionRecord,
    ContextInfo,
    EvaluationInfo,
    EvidenceInfo,
    ExecutionInfo,
    GroundTruthInfo,
    Isa95Info,
    LLMInfo,
    QuestionInfo,
    TraceInfo,
)


def _json_safe(value: Any) -> Any:
    """
    Best-effort recursive conversion to JSON-compatible primitives --
    `TraceEvent.result`/`arguments` are typed `Any` (a tool result can be
    a dict, list, scalar, or occasionally a non-JSON-native object like a
    datetime); round-tripping through `json.dumps(..., default=str)`
    guarantees the export is always plain JSON without silently dropping
    any field.
    """

    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def _trace_event_to_dict(event: TraceEvent) -> dict[str, Any]:
    data = event.model_dump(mode="json")
    return {key: _json_safe(value) for key, value in data.items()}


def _question_info(question: Question | None, fallback_question_id: str | None) -> QuestionInfo:
    if question is None:
        return QuestionInfo(
            id=fallback_question_id or "(unknown)",
            text=None,
            use_case=None,
            category=None,
            difficulty=None,
            expected_answer_type=None,
            tags=[],
            provenance=None,
        )

    tags = [tag.value for tag in question.tags]
    return QuestionInfo(
        id=question.question_id,
        text=question.question_text,
        use_case=question.use_case_id,
        category=tags[0] if tags else None,
        difficulty=question.difficulty.value,
        expected_answer_type=question.expected_answer_type.value,
        tags=tags,
        provenance=question.provenance,
    )


def _ground_truth_info(entry_correct_answer, question: Question | None, task: BenchmarkTask | None) -> GroundTruthInfo:
    expected_answer_type = question.expected_answer_type.value if question is not None else None
    source = None
    if task is not None:
        source = f"benchmark_task:{task.task_id}"
    elif entry_correct_answer is not None and entry_correct_answer.limitation is None:
        source = "scenario_ground_truth"

    if entry_correct_answer is None:
        return GroundTruthInfo(
            answer=None,
            expected_answer_type=expected_answer_type,
            root_cause_disturbance=None,
            affected_measurements=[],
            affected_equipment=[],
            expected_relationships=[],
            expected_evidence=[],
            source=None,
            explanation=None,
            limitation="No ground truth could be rendered for this run (no task/scenario resolved).",
        )

    return GroundTruthInfo(
        answer=entry_correct_answer.reference_conclusion if entry_correct_answer.limitation is None else None,
        expected_answer_type=expected_answer_type,
        root_cause_disturbance=entry_correct_answer.root_cause_disturbance,
        affected_measurements=list(entry_correct_answer.affected_measurements),
        affected_equipment=list(entry_correct_answer.affected_equipment),
        expected_relationships=list(entry_correct_answer.expected_relationships),
        expected_evidence=list(entry_correct_answer.expected_evidence),
        source=source,
        explanation=entry_correct_answer.reference_conclusion if entry_correct_answer.limitation is None else None,
        limitation=entry_correct_answer.limitation,
    )


def _is_correct(task: BenchmarkTask | None, record: ExperimentRecord) -> bool | None:
    """
    Applies the run's own task `EvaluationCriteria.binding_scores`/
    `pass_threshold` directly to THIS run's `EvaluationReport` -- the
    same binding criteria `icab.analysis.sufficiency` already applies at
    the aggregate level, here applied to one execution. `None` (never a
    guessed bool) when there is no task or no evaluation to check.
    """

    if task is None or record.evaluation is None:
        return None

    criteria = task.evaluation_criteria
    scores = [getattr(record.evaluation, name) for name in criteria.binding_scores]
    if any(score is None for score in scores):
        return None
    return all(score >= criteria.pass_threshold for score in scores)


def build_canonical_record(
    record: ExperimentRecord,
    trace: list[TraceEvent],
    *,
    question: Question | None,
    task: BenchmarkTask | None,
    campaign_id: str,
    benchmark_name: str,
    benchmark_version: str | None,
) -> CanonicalExecutionRecord:
    entry = build_qa_report_entry(record, task=task, scenario=None)

    tool_calls = [_trace_event_to_dict(event) for event in trace]
    retrievals = [call for call in tool_calls if call.get("context_acquired")]

    evaluation = record.evaluation
    context_acquired = list(evaluation.context_acquired) if evaluation is not None else []
    context_consumed = list(evaluation.context_consumed) if evaluation is not None else []
    retrieval_event_count = sum(1 for call in tool_calls if call.get("context_acquired") or call.get("context_consumed"))

    hypothesized = [dim.value for dim in question.hypothesized_required_context] if question is not None else []
    available = [dim.value for dim in provided_dimensions(record.config.architectures)]

    failure_category = classify_failures([record])[0].category
    failure_mode = None if failure_category == FailureCategory.NONE else failure_category

    evidence_items = (
        [f"{ev.source}:{ev.identifier}" for ev in record.result.evidence] if record.result is not None else []
    )
    evidence_sources = sorted({ev.source for ev in record.result.evidence}) if record.result is not None else []

    return CanonicalExecutionRecord(
        execution_id=record.run_id,
        benchmark=BenchmarkInfo(name=benchmark_name, version=benchmark_version, campaign_id=campaign_id),
        isa95=Isa95Info(level=record.config.isa95_level or "(unknown)"),
        question=_question_info(question, record.config.question_id),
        ground_truth=_ground_truth_info(entry.correct_answer, question, task),
        llm=LLMInfo(
            model=record.config.llm_model,
            agent=record.config.agent_type.value,
            answer=entry.agent_answer,
        ),
        execution=ExecutionInfo(
            repetition=record.config.repetition,
            repetition_mode=record.config.repetition_mode,
            scenario=record.config.scenario_id,
            architecture="+".join(record.config.architectures),
            timestamp_started=record.started_at.isoformat(),
            timestamp_completed=record.completed_at.isoformat(),
            latency_ms=record.total_latency_ms,
            success=record.status == ExperimentRunStatus.COMPLETED,
        ),
        context=ContextInfo(
            hypothesized_required_dimensions=hypothesized,
            available_dimensions=available,
            context_acquired=context_acquired,
            context_consumed=context_consumed,
            context_retrieval_events=retrieval_event_count,
        ),
        evidence=EvidenceInfo(items=evidence_items, sources=evidence_sources),
        trace=TraceInfo(
            tool_calls=tool_calls,
            retrievals=retrievals,
            errors=[record.error] if record.error else [],
        ),
        evaluation=EvaluationInfo(
            correct=_is_correct(task, record),
            answer_score=evaluation.conclusion_correctness_score if evaluation is not None else None,
            canonical_id_score=evaluation.canonical_id_score if evaluation is not None else None,
            evidence_score=evaluation.required_evidence_score if evaluation is not None else None,
            failure_mode=failure_mode,
            evaluation_details=_json_safe(evaluation.model_dump(mode="json")) if evaluation is not None else None,
        ),
    )
