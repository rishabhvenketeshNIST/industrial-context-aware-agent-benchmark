"""
M13-D (follow-up): a researcher-facing "benchmark question/answer"
report -- one entry per persisted run showing exactly what question the
agent was asked, what it answered, what the correct answer/ground truth
actually was, what evidence was required vs. actually provided, and that
run's own deterministic metrics -- plus an overall summary at the bottom.

This is a RESEARCHER-ONLY artifact. It is built entirely from already-
persisted `ExperimentRecord`s (produced by an agent run that never had
access to `ground_truth`) -- building this report makes no gateway/agent/
LLM call itself, so it cannot leak ground truth back to an agent; see
`tests/unit/reporting/test_qa_report.py::TestGroundTruthNeverReachesTheAgent`
for the end-to-end check (mocked LLM messages vs. this report's own
rendered content).

Computes no new score -- every metric here is read directly off the
existing `EvaluationReport` (M8/M13-C, `GroundedInvestigationEvaluator`)
and `ExperimentRecord`, and the bottom-of-report aggregate breakdowns are
the existing `icab.reporting.aggregation.aggregate_records` (M12),
reused rather than re-implemented.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from icab.experiments.models import ExperimentRecord, ExperimentRunStatus
from icab.scenarios.models import BenchmarkScenario, GroundTruth
from icab.tasks.benchmark_task import BenchmarkTask

from .aggregation import AggregationReport, aggregate_records

#: Metrics shown in each entry's own per-task table -- exactly the six
#: EvaluationReport scores plus the efficiency figures the M13-D spec
#: calls out ("at minimum"), read directly off the existing, already-
#: computed EvaluationReport/ExperimentRecord -- nothing new computed.
_ENTRY_METRIC_LABELS: tuple[tuple[str, str], ...] = (
    ("required_evidence_score", "Required evidence score"),
    ("canonical_id_score", "Canonical id score"),
    ("relationship_score", "Relationship score"),
    ("conclusion_correctness_score", "Conclusion correctness score"),
    ("grounding_score", "Grounding score"),
    ("completeness_score", "Completeness score"),
)

#: Clarifying suffixes appended to specific metric ROW LABELS in the
#: rendered Markdown table only -- never changes `QAReportEntry.metrics`'
#: underlying dict keys/JSON. Added after a researcher flagged
#: `context_consumed=0` on a single-tool-call run (nothing else to
#: "consume" -- see the glossary this module's markdown renders, and
#: docs/architecture/llm-agent.md#context_acquired-vs-context_consumed
#: for the full audit) as looking like a bug when it is the CORRECT
#: value under context_consumed's actual, narrower definition.
_METRIC_ROW_NOTES: dict[str, str] = {
    "context_acquired": "ids THIS trace's tool calls each individually learned about",
    "context_consumed": (
        "discovery→retrieval hand-offs only -- NOT whether the "
        "conclusion used its evidence (see required_evidence_score/"
        "grounding_score above, and the glossary at the top of this report)"
    ),
}

#: The three breakdowns the M13-D follow-up asks for at the bottom of
#: the report, plus a single-group "overall" grouping (every benchmark
#: invocation shares one `suite`, so grouping by it alone yields exactly
#: one group spanning every included run).
_OVERALL_GROUP_BY: tuple[str, ...] = ("suite",)
_BREAKDOWN_GROUP_BYS: tuple[tuple[str, str], ...] = (
    ("architecture", "By architecture"),
    ("difficulty", "By difficulty"),
    ("task_type", "By task type"),
)


class CorrectAnswer(BaseModel):
    """
    A `GroundTruth` (or a bare scenario's, if the run has no task)
    rendered into researcher-readable text -- never a raw model dump.
    Only fields actually present on the ground truth are rendered;
    nothing here is inferred or invented.
    """

    model_config = ConfigDict(extra="forbid")

    #: The ground truth's own reference conclusion -- already
    #: human-authored prose (e.g. "Reactor pressure is near its nominal
    #: ... value ..., well below the 3000 kPa high-pressure trip
    #: threshold"), so this alone is often a complete, readable answer.
    reference_conclusion: str
    root_cause_disturbance: str | None = None
    affected_measurements: list[str] = Field(default_factory=list)
    affected_equipment: list[str] = Field(default_factory=list)
    #: Rendered "subject --[predicate]--> object" strings, not raw tuples.
    expected_relationships: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    #: Set when the underlying task/scenario ground truth couldn't be
    #: resolved at all (e.g. neither a task nor a scenario registry had
    #: this run's ids) -- the report says so explicitly rather than
    #: fabricating a correct answer.
    limitation: str | None = None


class QAReportEntry(BaseModel):
    """One persisted run, rendered for a researcher to inspect directly."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str | None
    scenario_id: str
    difficulty: str
    task_type: str | None
    architecture: str
    seed: int
    fault_id: str | None

    status: str
    error: str | None

    objective: str
    #: The agent's own final answer, VERBATIM -- never paraphrased,
    #: truncated, or re-summarized. None only when the run failed before
    #: producing any InvestigationResult at all.
    agent_answer: str | None
    correct_answer: CorrectAnswer | None

    required_evidence: list[str]
    evidence_provided: list[str]

    #: metric name -> value, only for metrics the evaluator actually
    #: computed for this run (empty for a failed/un-evaluated run).
    metrics: dict[str, float | int | None]


class QAReport(BaseModel):
    """The full researcher-facing report: one entry per run, plus an overall summary."""

    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    entries: list[QAReportEntry]

    total_runs: int
    successful_runs: int
    failed_runs: int
    skipped_runs: int

    overall: AggregationReport | None
    by_architecture: AggregationReport | None
    by_difficulty: AggregationReport | None
    by_task_type: AggregationReport | None


def _render_ground_truth(ground_truth: GroundTruth) -> CorrectAnswer:
    return CorrectAnswer(
        reference_conclusion=ground_truth.conclusion,
        root_cause_disturbance=ground_truth.root_cause_disturbance,
        affected_measurements=list(ground_truth.affected_measurements),
        affected_equipment=list(ground_truth.affected_equipment),
        expected_relationships=[
            f"{subject} --[{predicate}]--> {object_}"
            for subject, predicate, object_ in ground_truth.expected_relationships
        ],
        expected_evidence=list(ground_truth.expected_evidence),
    )


def _correct_answer_for(
    record: ExperimentRecord,
    *,
    task: BenchmarkTask | None,
    scenario: BenchmarkScenario | None,
) -> CorrectAnswer:
    if task is not None:
        return _render_ground_truth(task.ground_truth)
    if scenario is not None:
        return _render_ground_truth(scenario.ground_truth)
    return CorrectAnswer(
        reference_conclusion="(unavailable)",
        limitation=(
            f"Neither a BenchmarkTask (task_id={record.config.task_id!r}) nor a "
            f"BenchmarkScenario (scenario_id={record.config.scenario_id!r}) could be "
            "resolved for this run, so no ground truth could be rendered -- this is a "
            "reporting-time limitation, not evidence the run itself lacked ground truth."
        ),
    )


def _required_evidence_for(task: BenchmarkTask | None, scenario: BenchmarkScenario | None) -> list[str]:
    if task is not None:
        return list(task.required_evidence)
    if scenario is not None:
        return list(scenario.ground_truth.expected_evidence)
    return []


def _entry_metrics(record: ExperimentRecord) -> dict[str, float | int | None]:
    metrics: dict[str, float | int | None] = {}
    evaluation = record.evaluation

    for name, _label in _ENTRY_METRIC_LABELS:
        metrics[name] = getattr(evaluation, name) if evaluation is not None else None

    metrics["tool_call_count"] = evaluation.tool_call_count if evaluation is not None else None
    metrics["context_acquired"] = len(evaluation.context_acquired) if evaluation is not None else None
    metrics["context_consumed"] = len(evaluation.context_consumed) if evaluation is not None else None
    metrics["latency_ms"] = record.total_latency_ms
    metrics["total_tokens"] = record.total_tokens

    return metrics


def build_qa_report_entry(
    record: ExperimentRecord,
    *,
    task: BenchmarkTask | None = None,
    scenario: BenchmarkScenario | None = None,
) -> QAReportEntry:
    """
    Builds one `QAReportEntry` from an already-persisted `ExperimentRecord`
    -- reads only what the run already produced (result/evaluation/trace
    totals); computes nothing new and makes no agent/gateway/LLM call.
    """

    config = record.config
    objective = task.objective if task is not None else (scenario.objective if scenario is not None else "(unavailable)")

    return QAReportEntry(
        run_id=record.run_id,
        task_id=config.task_id,
        scenario_id=config.scenario_id,
        difficulty=record.scenario_difficulty,
        task_type=config.task_type,
        architecture="+".join(config.architectures),
        seed=record.simulation_seed,
        fault_id=record.fault_id,
        status=record.status.value,
        error=record.error,
        objective=objective,
        agent_answer=record.result.conclusion if record.result is not None else None,
        correct_answer=_correct_answer_for(record, task=task, scenario=scenario),
        required_evidence=_required_evidence_for(task, scenario),
        evidence_provided=(
            [f"{evidence.source}: {evidence.identifier}" for evidence in record.result.evidence]
            if record.result is not None
            else []
        ),
        metrics=_entry_metrics(record),
    )


def build_qa_report(
    records: list[ExperimentRecord],
    *,
    benchmark_id: str,
    successful_runs: int,
    failed_runs: int,
    skipped_runs: int,
    tasks_by_id: dict[str, BenchmarkTask] | None = None,
    scenarios_by_id: dict[str, BenchmarkScenario] | None = None,
) -> QAReport:
    """
    Builds the full researcher-facing report over `records` (typically
    every record one `BenchmarkRunner.run()` invocation just produced).
    `tasks_by_id`/`scenarios_by_id` are plain lookup dicts (not registries
    themselves) so this stays independent of how the caller obtained them
    -- `icab.benchmark.runner.BenchmarkRunner` already has both loaded for
    the invocation and passes them straight through.
    """

    tasks_by_id = tasks_by_id or {}
    scenarios_by_id = scenarios_by_id or {}

    entries = [
        build_qa_report_entry(
            record,
            task=tasks_by_id.get(record.config.task_id) if record.config.task_id else None,
            scenario=scenarios_by_id.get(record.config.scenario_id),
        )
        for record in records
    ]

    def _aggregate(group_by: tuple[str, ...]) -> AggregationReport | None:
        if not records:
            return None
        return aggregate_records(records, group_by=group_by, allow_heterogeneous_controls=True)

    return QAReport(
        benchmark_id=benchmark_id,
        entries=entries,
        total_runs=successful_runs + failed_runs + skipped_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        skipped_runs=skipped_runs,
        overall=_aggregate(_OVERALL_GROUP_BY),
        by_architecture=_aggregate(("architecture",)),
        by_difficulty=_aggregate(("difficulty",)),
        by_task_type=_aggregate(("task_type",)),
    )


def _render_correct_answer(answer: CorrectAnswer | None) -> list[str]:
    if answer is None:
        return ["- _(no ground truth available)_"]

    if answer.limitation is not None:
        return [f"- **Limitation:** {answer.limitation}"]

    lines = [f"- **Reference conclusion:** {answer.reference_conclusion}"]
    if answer.root_cause_disturbance is not None:
        lines.append(f"- **Root cause disturbance:** `{answer.root_cause_disturbance}`")
    if answer.affected_measurements:
        lines.append(f"- **Affected measurements:** {', '.join(f'`{m}`' for m in answer.affected_measurements)}")
    if answer.affected_equipment:
        lines.append(f"- **Affected equipment:** {', '.join(f'`{e}`' for e in answer.affected_equipment)}")
    if answer.expected_relationships:
        lines.append("- **Expected relationships:**")
        lines.extend(f"  - `{relationship}`" for relationship in answer.expected_relationships)
    if answer.expected_evidence:
        lines.append(f"- **Expected evidence:** {', '.join(f'`{e}`' for e in answer.expected_evidence)}")
    return lines


def _render_entry(entry: QAReportEntry) -> list[str]:
    lines = [
        f"## {entry.task_id or entry.scenario_id} -- `{entry.run_id}`",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Task ID | {entry.task_id or '(scenario-only run)'} |",
        f"| Scenario ID | {entry.scenario_id} |",
        f"| Difficulty | {entry.difficulty} |",
        f"| Task type | {entry.task_type or 'n/a'} |",
        f"| Architecture | {entry.architecture} |",
        f"| Seed | {entry.seed} |",
        f"| Fault ID | {entry.fault_id or '(none)'} |",
        f"| Status | {entry.status} |",
        "",
        "**Question presented to the agent:**",
        "",
        f"> {entry.objective}",
        "",
    ]

    if entry.status != ExperimentRunStatus.COMPLETED.value:
        lines += [
            f"**This run FAILED -- no agent answer or evaluation was produced.**",
            "",
            f"> {entry.error or '(no error message recorded)'}",
            "",
        ]
        return lines

    lines += [
        "**Agent's answer (verbatim):**",
        "",
        f"> {entry.agent_answer or '(empty)'}",
        "",
        "**Correct answer (ground truth):**",
        "",
        *_render_correct_answer(entry.correct_answer),
        "",
        f"**Required evidence:** {', '.join(f'`{e}`' for e in entry.required_evidence) or '(none)'}",
        "",
        f"**Evidence provided by the agent:** {', '.join(entry.evidence_provided) or '(none)'}",
        "",
        "**Metrics:**",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for name, value in entry.metrics.items():
        display = "n/a" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))
        note = _METRIC_ROW_NOTES.get(name)
        label = f"{name} _({note})_" if note else name
        lines.append(f"| {label} | {display} |")
    lines.append("")

    return lines


def _render_breakdown(title: str, report: AggregationReport | None) -> list[str]:
    if report is None:
        return []

    lines = [f"### {title}", ""]
    for group in report.groups:
        key = ", ".join(f"{k}={v}" for k, v in group.group_key.items())
        lines.append(
            f"- **{key}**: n={group.n_runs} (completed={group.n_completed}, failed={group.n_failed})"
        )
        for metric_name, stats in group.metrics.items():
            if stats.n == 0:
                continue
            mean_display = f"{stats.mean:.3f}" if stats.mean is not None else "n/a"
            lines.append(f"  - {metric_name}: mean={mean_display} (n={stats.n})")
    lines.append("")
    return lines


def render_qa_report_markdown(report: QAReport) -> str:
    """
    Renders a `QAReport` as researcher-facing Markdown: one section per
    run (question/agent answer/correct answer/evidence/metrics), then an
    overall summary at the bottom (run counts + architecture/difficulty/
    task-type breakdowns) -- purely a text-formatting layer, computing
    nothing beyond what `build_qa_report` already produced.
    """

    lines = [
        f"# Benchmark question/answer report: {report.benchmark_id}",
        "",
        (
            "Researcher-only artifact -- the ground truth shown below was "
            "NEVER visible to the agent during its run; see "
            "`tests/unit/reporting/test_qa_report.py` for the isolation check."
        ),
        "",
        (
            "**Reading `context_acquired`/`context_consumed` below:** "
            "`context_acquired` counts distinct ids THIS run's tool calls "
            "individually learned about. `context_consumed` counts "
            "discovery→retrieval hand-offs ONLY -- an id an earlier "
            "browse/relationship call acquired, later exploited by a "
            "specific value-retrieval call in the SAME trace -- it is "
            "**not** a judgment about whether the conclusion actually used "
            "its evidence. A run with `context_acquired=1, "
            "context_consumed=0` after exactly one direct tool call (no "
            "discovery step) is expected, not a defect: check "
            "`required_evidence_score`/`grounding_score` and \"Evidence "
            "provided by the agent\" below for whether acquired evidence "
            "was actually used. See "
            "`docs/architecture/llm-agent.md#context_acquired-vs-context_consumed` "
            "for the full audit."
        ),
        "",
        "---",
        "",
    ]

    for entry in report.entries:
        lines += _render_entry(entry)
        lines.append("---")
        lines.append("")

    lines += [
        "## Overall summary",
        "",
        f"- **Total runs:** {report.total_runs}",
        f"- **Successful:** {report.successful_runs}",
        f"- **Failed:** {report.failed_runs}",
        f"- **Skipped:** {report.skipped_runs}",
        "",
    ]
    lines += _render_breakdown("By architecture", report.by_architecture)
    lines += _render_breakdown("By difficulty", report.by_difficulty)
    lines += _render_breakdown("By task type", report.by_task_type)

    return "\n".join(lines)
