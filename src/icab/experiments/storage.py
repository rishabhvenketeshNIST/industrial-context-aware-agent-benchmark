"""
Persists M9 experiment results using ICAB's existing `results/` directory,
with a clear separation between raw run data, traces, evaluation results,
and aggregate (cross-run) results -- reusing
`icab.trace.storage.JsonlTraceStorage` for the trace files rather than a
second trace-serialization format.

    results/
      raw/<run_id>.json          ExperimentRecord (trace NOT embedded)
      traces/<run_id>.jsonl      the run's TraceEvent list (JsonlTraceStorage)
      evaluations/<run_id>.json  the run's EvaluationReport alone
      aggregate/<experiment_id>.json / .csv   cross-run comparison tables
      hypotheses/<experiment_id>-<hypothesis>.json  M11 HypothesisTestResult
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from icab.trace.models import TraceEvent
from icab.trace.storage import JsonlTraceStorage

from .hypotheses import HypothesisTestResult
from .models import ExperimentRecord, RunValidity

#: Flat columns written by `write_aggregate_csv`, one row per run. Kept
#: explicit (rather than "whatever keys happen to be present") so the CSV
#: schema is stable across experiments.
AGGREGATE_CSV_COLUMNS = (
    "run_id",
    "experiment_id",
    "scenario_id",
    "scenario_difficulty",
    "architectures",
    "architecture_combination_key",
    "agent_type",
    "deterministic_agent",
    "llm_model",
    "llm_temperature",
    "max_steps",
    "simulation_seed",
    "random_seed",
    "status",
    "validity",
    "validity_reason",
    "error",
    "started_at",
    "completed_at",
    "termination",
    "required_evidence_score",
    "canonical_id_score",
    "relationship_score",
    "conclusion_correctness_score",
    "grounding_score",
    "completeness_score",
    "temporal_evidence_required",
    "temporal_evidence_acquired",
    "tool_call_count",
    "trace_event_count",
    "discovered_canonical_id_count",
    "acquisition_count",
    "redundant_acquisition_count",
    "unresolved_acquisition_count",
    "tool_error_count",
    "total_latency_ms",
    "total_tokens",
)


#: Fields that must be held equal across every run in a comparison for it
#: to be a valid architecture comparison -- i.e. the "everything else held
#: constant" side of "varying only architecture" (see docs/research/
#: experiment-plan.md). `objective` isn't listed separately because it's
#: determined by `scenario_id` (same scenario => same objective).
_CONTROL_FIELDS: tuple[str, ...] = (
    "scenario_id",
    "simulation_seed",
    "llm_model",
    "llm_temperature",
    "max_steps",
)


class HeterogeneousControlsError(ValueError):
    """
    Raised by `write_aggregate` when the runs being aggregated do not hold
    `_CONTROL_FIELDS` constant and `allow_heterogeneous_controls` was not
    passed -- i.e. this would not be a valid "vary only architecture"
    comparison. Pass `allow_heterogeneous_controls=True` to aggregate such
    runs anyway (e.g. a deliberately mixed sweep); the written JSON still
    records `controls_consistent`/`control_variance` either way.
    """


def _control_value(record: ExperimentRecord, field: str) -> object:
    if field == "scenario_id":
        return record.config.scenario_id
    if field == "simulation_seed":
        return record.simulation_seed
    if field == "llm_model":
        return record.config.llm_model
    if field == "llm_temperature":
        return record.config.llm_temperature
    if field == "max_steps":
        return record.config.max_steps
    raise ValueError(f"Unknown control field: {field}")  # pragma: no cover


def _control_variance(records: list[ExperimentRecord]) -> dict[str, list]:
    """Which `_CONTROL_FIELDS` differ across `records`, and their distinct values."""

    variance: dict[str, list] = {}
    for field in _CONTROL_FIELDS:
        values = {_control_value(record, field) for record in records}
        if len(values) > 1:
            variance[field] = sorted(values, key=str)
    return variance


class ExperimentResultStore:
    """Reads/writes ExperimentRecords and their traces under a results/ root."""

    def __init__(self, root: str | Path = "results") -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.traces_dir = self.root / "traces"
        self.evaluations_dir = self.root / "evaluations"
        self.aggregate_dir = self.root / "aggregate"
        self.hypotheses_dir = self.root / "hypotheses"
        self._trace_storage = JsonlTraceStorage()

    def save(self, record: ExperimentRecord, trace: list[TraceEvent]) -> None:
        """Persist one run's record, trace, and evaluation under their respective subdirs."""

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        (self.raw_dir / f"{record.run_id}.json").write_text(
            record.model_dump_json(indent=2, exclude={"evaluation"}),
            encoding="utf-8",
        )

        self._trace_storage.write(self.traces_dir / f"{record.run_id}.jsonl", trace)

        if record.evaluation is not None:
            self.evaluations_dir.mkdir(parents=True, exist_ok=True)
            (self.evaluations_dir / f"{record.run_id}.json").write_text(
                record.evaluation.model_dump_json(indent=2),
                encoding="utf-8",
            )

    def load_record(self, run_id: str) -> ExperimentRecord:
        """Load a run's record (without its evaluation -- see load_evaluation)."""

        data = json.loads((self.raw_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        evaluation_path = self.evaluations_dir / f"{run_id}.json"

        if evaluation_path.exists():
            data["evaluation"] = json.loads(evaluation_path.read_text(encoding="utf-8"))

        return ExperimentRecord.model_validate(data)

    def load_trace(self, run_id: str) -> list[TraceEvent]:
        return self._trace_storage.read(self.traces_dir / f"{run_id}.jsonl")

    def list_run_ids(self) -> list[str]:
        if not self.raw_dir.exists():
            return []
        return sorted(path.stem for path in self.raw_dir.glob("*.json"))

    def write_aggregate(
        self,
        experiment_id: str,
        records: list[ExperimentRecord],
        *,
        include_invalid: bool = False,
        allow_heterogeneous_controls: bool = False,
    ) -> tuple[Path, Path]:
        """
        Write a cross-run comparison table for ``records`` (typically all
        runs sharing ``experiment_id``) as both JSON and CSV under
        `results/aggregate/`. Returns ``(json_path, csv_path)``.

        By default, runs with ``validity != RunValidity.VALID`` (e.g. a
        legacy deterministic baseline against a real scenario -- see
        ``icab.experiments.models.RunValidity`` and
        docs/research/experiment-plan.md) are EXCLUDED from this table --
        the main architecture-comparison benchmark must not silently
        include a run that cannot access the scenario's actual data. Those
        runs are still fully persisted (`save()` writes their raw/trace/
        evaluation files regardless); they're just kept out of the
        comparison table unless ``include_invalid=True`` is passed
        explicitly, in which case their `validity`/`validity_reason`
        columns make them clearly identifiable rather than blending in.

        Also by default, this refuses (raises `HeterogeneousControlsError`)
        to aggregate runs whose `_CONTROL_FIELDS` (scenario, simulation
        seed, LLM model/temperature, step budget) are not identical across
        the included runs -- an architecture comparison is only valid when
        everything except `architectures` is held constant. Pass
        ``allow_heterogeneous_controls=True`` to aggregate anyway (e.g. a
        deliberately mixed sweep); the written JSON always records
        ``controls_consistent``/``control_variance`` so this is auditable
        either way.
        """

        self.aggregate_dir.mkdir(parents=True, exist_ok=True)

        json_path = self.aggregate_dir / f"{experiment_id}.json"
        csv_path = self.aggregate_dir / f"{experiment_id}.csv"

        included = [
            record
            for record in records
            if include_invalid or record.validity == RunValidity.VALID
        ]
        excluded_count = len(records) - len(included)

        variance = _control_variance(included) if included else {}
        if variance and not allow_heterogeneous_controls:
            raise HeterogeneousControlsError(
                f"Runs being aggregated under {experiment_id!r} do not hold "
                f"controls constant: {variance}. This is not a valid "
                "'vary only architecture' comparison -- see "
                "docs/research/experiment-plan.md. Pass "
                "allow_heterogeneous_controls=True to aggregate anyway."
            )

        rows = [self._flatten(record) for record in included]

        json_path.write_text(
            json.dumps(
                {
                    "experiment_id": experiment_id,
                    "excluded_invalid_runs": excluded_count,
                    "controls_consistent": not variance,
                    "control_variance": variance,
                    "runs": rows,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        with csv_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=AGGREGATE_CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in AGGREGATE_CSV_COLUMNS})

        return json_path, csv_path

    @staticmethod
    def _flatten(record: ExperimentRecord) -> dict:
        evaluation = record.evaluation
        result = record.result
        information_flow = record.information_flow

        return {
            "run_id": record.run_id,
            "experiment_id": record.experiment_id,
            "scenario_id": record.config.scenario_id,
            "scenario_difficulty": record.scenario_difficulty,
            "architectures": "+".join(record.config.architectures),
            "architecture_combination_key": record.config.architecture_combination_key or "",
            "agent_type": record.config.agent_type.value,
            "deterministic_agent": (
                record.config.deterministic_agent.value
                if record.config.deterministic_agent
                else ""
            ),
            "llm_model": record.config.llm_model or "",
            "llm_temperature": record.config.llm_temperature,
            "max_steps": record.config.max_steps,
            "simulation_seed": record.simulation_seed,
            "random_seed": record.config.random_seed,
            "status": record.status.value,
            "validity": record.validity.value,
            "validity_reason": record.validity_reason or "",
            "error": record.error or "",
            "started_at": record.started_at.isoformat(),
            "completed_at": record.completed_at.isoformat(),
            "termination": result.termination.value if result else "",
            "required_evidence_score": evaluation.required_evidence_score if evaluation else "",
            "canonical_id_score": evaluation.canonical_id_score if evaluation else "",
            "relationship_score": evaluation.relationship_score if evaluation else "",
            "conclusion_correctness_score": (
                evaluation.conclusion_correctness_score if evaluation else ""
            ),
            "grounding_score": evaluation.grounding_score if evaluation else "",
            "completeness_score": evaluation.completeness_score if evaluation else "",
            "temporal_evidence_required": (
                evaluation.temporal_evidence_required if evaluation else ""
            ),
            "temporal_evidence_acquired": (
                evaluation.temporal_evidence_acquired if evaluation else ""
            ),
            "tool_call_count": evaluation.tool_call_count if evaluation else "",
            "trace_event_count": record.trace_event_count,
            "discovered_canonical_id_count": (
                len(information_flow.discovered_canonical_ids) if information_flow else ""
            ),
            "acquisition_count": len(information_flow.acquisitions) if information_flow else "",
            "redundant_acquisition_count": (
                information_flow.redundant_acquisition_count if information_flow else ""
            ),
            "unresolved_acquisition_count": (
                information_flow.unresolved_acquisition_count if information_flow else ""
            ),
            "tool_error_count": information_flow.tool_error_count if information_flow else "",
            "total_latency_ms": record.total_latency_ms if record.total_latency_ms is not None else "",
            "total_tokens": record.total_tokens if record.total_tokens is not None else "",
        }

    def write_hypothesis_result(
        self,
        result: HypothesisTestResult,
        *,
        experiment_id: str,
    ) -> Path:
        """
        Persist one M11 `HypothesisTestResult` under `results/hypotheses/`,
        named `<experiment_id>-<hypothesis>.json`. `experiment_id` is
        supplied by the caller (typically the same id used for the
        `compare_combinations` run(s) the result was computed from)
        rather than embedded in the result itself, since one result can
        legitimately be recomputed from records spanning several
        experiment ids.
        """

        self.hypotheses_dir.mkdir(parents=True, exist_ok=True)

        path = self.hypotheses_dir / f"{experiment_id}-{result.hypothesis.value}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        return path

    def load_hypothesis_result(self, experiment_id: str, hypothesis: str) -> HypothesisTestResult:
        path = self.hypotheses_dir / f"{experiment_id}-{hypothesis}.json"
        return HypothesisTestResult.model_validate_json(path.read_text(encoding="utf-8"))
