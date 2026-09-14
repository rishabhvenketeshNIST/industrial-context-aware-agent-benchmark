"""
The canonical, standalone execution-record schema: one JSON object per
run, containing everything an external researcher needs (question,
ground truth, LLM answer, execution/context/evidence/trace/evaluation
info) WITHOUT importing any ICAB Python class.

Every field here is built ONLY from data an existing ICAB run already
produced (`icab.experiments.models.ExperimentRecord`, its trace, the
`icab.questions.models.Question` it answers, and the
`icab.tasks.benchmark_task.BenchmarkTask` that concretely realized it --
see `icab.export.build`). Nothing is invented: a field with no existing
ICAB analog is always `None` (JSON `null`), never guessed. See each
model's own docstring for which fields are currently unavailable and
why -- that limitation is real, not a placeholder to fill in later
without also updating the underlying ICAB data model.

Every model here uses only JSON-compatible primitives (str / int / float
/ bool / None / list / dict) -- no ICAB enum/Pydantic object is ever
embedded directly, so `CanonicalExecutionRecord.model_dump(mode="json")`
(or the persisted `.json`) is fully self-describing and can be parsed by
`json.load()` alone, in any language, with no ICAB import.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

#: Bumped only if this schema's SHAPE changes (field added/removed/
#: renamed) -- recorded on every campaign manifest
#: (`icab.export.schema.BenchmarkManifestExport.output_schema_version`)
#: so a downstream analysis script can check compatibility before
#: parsing a dataset produced by a different ICAB version.
EXPORT_SCHEMA_VERSION = "1.0.0"


class BenchmarkInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str | None
    campaign_id: str


class Isa95Info(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str


class QuestionInfo(BaseModel):
    """
    The semantic question this execution answers -- straight off
    `icab.questions.models.Question`. `category` is the FIRST of the
    question's own `tags` (its primary taxonomy label); `tags` carries
    the full list separately -- Question has no independent singular
    "category" field of its own, so this is a documented derivation,
    not a second, invented field.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    text: str | None
    use_case: str | None
    category: str | None
    difficulty: str | None
    expected_answer_type: str | None
    tags: list[str]
    provenance: str | None


class GroundTruthInfo(BaseModel):
    """
    The correct answer, exported SEPARATELY from the LLM's answer, never
    leaked to the agent during execution (ground truth is read here only
    from the already-persisted, researcher-only task/scenario ground
    truth -- see `icab.reporting.qa_report`, reused directly by
    `icab.export.build`).

    `unit` and `acceptable_range` have no ICAB analog today (ground
    truth is a structured conclusion + canonical-id evidence, not a
    numeric value/unit/tolerance) -- always `null`, never guessed.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str | None
    unit: str | None = None
    acceptable_range: list[float] | None = None
    expected_answer_type: str | None
    root_cause_disturbance: str | None
    affected_measurements: list[str]
    affected_equipment: list[str]
    expected_relationships: list[str]
    expected_evidence: list[str]
    source: str | None
    explanation: str | None
    #: Set (instead of fabricating an answer) when neither a
    #: BenchmarkTask nor a BenchmarkScenario could be resolved for this
    #: run -- mirrors `icab.reporting.qa_report.CorrectAnswer.limitation`.
    limitation: str | None = None


class LLMInfo(BaseModel):
    """
    `raw_response` is always `null`: ICAB's LLM agent currently persists
    only the structured `InvestigationResult.conclusion`, not the raw
    provider response payload -- this is a genuine ICAB limitation, not
    an export omission. See docs/benchmark/specification-v3.md.
    """

    model_config = ConfigDict(extra="forbid")

    model: str | None
    agent: str
    answer: str | None
    raw_response: None = None


class ExecutionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repetition: int | None
    repetition_mode: str | None
    scenario: str
    architecture: str
    timestamp_started: str
    timestamp_completed: str
    latency_ms: float | None
    success: bool


class ContextInfo(BaseModel):
    """
    `context_acquired`/`context_consumed` are the SAME fields ICAB's own
    trace/evaluation already track -- see
    docs/architecture/llm-agent.md#context_acquired-vs-context_consumed
    (`context_consumed` is discovery -> retrieval hand-offs ONLY, not
    whether the final conclusion actually used the evidence; preserved
    verbatim here, never redefined).
    """

    model_config = ConfigDict(extra="forbid")

    hypothesized_required_dimensions: list[str]
    available_dimensions: list[str]
    context_acquired: list[str]
    context_consumed: list[str]
    context_retrieval_events: int


class EvidenceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[str]
    sources: list[str]


class TraceInfo(BaseModel):
    """
    `tool_calls` is the run's full trace, sanitized to JSON-safe
    primitives (see `icab.export.build._json_safe`). `retrievals` is the
    subset of `tool_calls` whose own `context_acquired` was non-empty --
    not a separately-tracked signal. `errors` is this run's own
    `ExperimentRecord.error` (the run-level failure message), wrapped in
    a list, when present -- ICAB does not currently record per-tool-call
    error flags on `TraceEvent` itself, so per-call error detection is
    not attempted (never invented).
    """

    model_config = ConfigDict(extra="forbid")

    tool_calls: list[dict[str, Any]]
    retrievals: list[dict[str, Any]]
    errors: list[str]


class EvaluationInfo(BaseModel):
    """
    `correct` is computed by applying the run's own task
    `EvaluationCriteria.binding_scores`/`pass_threshold`
    (`icab.tasks.benchmark_task`) directly to this ONE run's
    `EvaluationReport` -- the exact same binding criteria
    `icab.analysis.sufficiency` already applies at the AGGREGATE level,
    here applied per-execution. `None` when no task or no evaluation is
    available for this run (never guessed as True/False).

    `evaluation_details` carries the complete, already-computed
    `EvaluationReport` (JSON-safe dump) for anything not surfaced by the
    named fields above -- no evaluator score is left out, and none is
    recomputed.
    """

    model_config = ConfigDict(extra="forbid")

    correct: bool | None
    answer_score: float | None
    canonical_id_score: float | None
    evidence_score: float | None
    failure_mode: str | None
    evaluation_details: dict[str, Any] | None


class CanonicalExecutionRecord(BaseModel):
    """One execution, fully self-contained -- see module docstring."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = EXPORT_SCHEMA_VERSION
    execution_id: str

    benchmark: BenchmarkInfo
    isa95: Isa95Info
    question: QuestionInfo
    ground_truth: GroundTruthInfo
    llm: LLMInfo
    execution: ExecutionInfo
    context: ContextInfo
    evidence: EvidenceInfo
    trace: TraceInfo
    evaluation: EvaluationInfo
