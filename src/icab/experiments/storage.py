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
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from icab.trace.models import TraceEvent
from icab.trace.storage import JsonlTraceStorage

from .models import ExperimentRecord

#: Flat columns written by `write_aggregate_csv`, one row per run. Kept
#: explicit (rather than "whatever keys happen to be present") so the CSV
#: schema is stable across experiments.
AGGREGATE_CSV_COLUMNS = (
    "run_id",
    "experiment_id",
    "scenario_id",
    "scenario_difficulty",
    "architectures",
    "agent_type",
    "deterministic_agent",
    "llm_model",
    "llm_temperature",
    "max_steps",
    "simulation_seed",
    "random_seed",
    "status",
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
)


class ExperimentResultStore:
    """Reads/writes ExperimentRecords and their traces under a results/ root."""

    def __init__(self, root: str | Path = "results") -> None:
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.traces_dir = self.root / "traces"
        self.evaluations_dir = self.root / "evaluations"
        self.aggregate_dir = self.root / "aggregate"
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
    ) -> tuple[Path, Path]:
        """
        Write a cross-run comparison table for ``records`` (typically all
        runs sharing ``experiment_id``) as both JSON and CSV under
        `results/aggregate/`. Returns ``(json_path, csv_path)``.
        """

        self.aggregate_dir.mkdir(parents=True, exist_ok=True)

        json_path = self.aggregate_dir / f"{experiment_id}.json"
        csv_path = self.aggregate_dir / f"{experiment_id}.csv"

        rows = [self._flatten(record) for record in records]

        json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

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

        return {
            "run_id": record.run_id,
            "experiment_id": record.experiment_id,
            "scenario_id": record.config.scenario_id,
            "scenario_difficulty": record.scenario_difficulty,
            "architectures": "+".join(record.config.architectures),
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
        }
