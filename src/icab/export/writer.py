"""
Writes one campaign's full standalone export tree under
`benchmark_exports/<isa95_level>/<campaign_id>/` (see module docstring
of `icab.export` and docs/benchmark/specification-v3.md) -- deliberately
a SEPARATE root from `results/` (ICAB's own internal experiment store):
this writer never reads from or writes into `results/`, and never
deletes/overwrites a previous campaign's export (see `CampaignExportWriter.write`).

    benchmark_exports/<level>/<campaign_id>/
      README.md
      benchmark_manifest.json
      questions.json
      ground_truth.json
      executions.jsonl
      results.json
      results.csv
      metrics.json
      q_and_a/<execution_id>.json
      q_and_a/<execution_id>.md
      traces/<execution_id>.json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from icab.questions.models import Question

from .metrics import build_campaign_metrics
from .schema import EXPORT_SCHEMA_VERSION, CanonicalExecutionRecord

#: `results.csv`'s exact, stable column order -- see the ICAB export
#: milestone spec's own suggested column list. Complex nested trace
#: structures deliberately stay OUT of the CSV (JSON/JSONL only).
RESULTS_CSV_COLUMNS = (
    "execution_id",
    "campaign_id",
    "isa95_level",
    "question_id",
    "question_text",
    "use_case",
    "category",
    "repetition",
    "repetition_mode",
    "scenario",
    "architecture",
    "agent",
    "model",
    "llm_answer",
    "ground_truth_answer",
    "expected_answer_type",
    "correct",
    "answer_score",
    "evidence_score",
    "canonical_id_score",
    "failure_mode",
    "latency_ms",
    "success",
)


class CampaignExportWriter:
    """Builds every file of one campaign's standalone export directory."""

    def __init__(self, *, output_root: str | Path = "benchmark_exports") -> None:
        self.output_root = Path(output_root)

    def campaign_dir(self, *, isa95_level: str, campaign_id: str) -> Path:
        return self.output_root / isa95_level / campaign_id

    def write(
        self,
        *,
        isa95_level: str,
        campaign_id: str,
        records: list[CanonicalExecutionRecord],
        planned_questions: list[Question],
        manifest_extra: dict[str, Any],
    ) -> Path:
        """
        Writes the full export tree and returns its directory. Safe to
        call again for the SAME campaign_id after a `--resume` run added
        more executions: existing per-execution files
        (`q_and_a/<id>.json`, `traces/<id>.json`) are never rewritten
        with different content for an id already on disk (an execution
        id, once written, is immutable -- see
        `icab.export.validation.validate_export`); the aggregate files
        (`executions.jsonl`, `results.*`, `metrics.json`,
        `README.md`) are always REGENERATED from the full current
        `records` list so they stay consistent with everything actually
        exported so far.
        """

        campaign_dir = self.campaign_dir(isa95_level=isa95_level, campaign_id=campaign_id)
        qa_dir = campaign_dir / "q_and_a"
        traces_dir = campaign_dir / "traces"
        qa_dir.mkdir(parents=True, exist_ok=True)
        traces_dir.mkdir(parents=True, exist_ok=True)

        records = sorted(records, key=lambda r: r.execution_id)

        self._write_questions(campaign_dir, planned_questions)
        self._write_ground_truth(campaign_dir, records)
        self._write_executions_jsonl(campaign_dir, records)
        self._write_results_json(campaign_dir, campaign_id, isa95_level, records)
        self._write_results_csv(campaign_dir, campaign_id, isa95_level, records)
        metrics = build_campaign_metrics(records)
        self._write_json(campaign_dir / "metrics.json", metrics)
        self._write_per_execution_files(qa_dir, traces_dir, records)
        manifest = self._write_manifest(campaign_dir, isa95_level, campaign_id, records, planned_questions, manifest_extra)
        self._write_readme(campaign_dir, isa95_level, campaign_id, records, manifest, metrics)

        return campaign_dir

    # -- individual files -------------------------------------------------

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _write_questions(self, campaign_dir: Path, questions: list[Question]) -> None:
        data = [
            {
                "question_id": q.question_id,
                "use_case_id": q.use_case_id,
                "isa95_level": q.isa95_level.value,
                "question_text": q.question_text,
                "task_type": q.task_type.value,
                "objective": q.objective,
                "hypothesized_required_context": [d.value for d in q.hypothesized_required_context],
                "expected_evidence_description": q.expected_evidence_description,
                "expected_answer_type": q.expected_answer_type.value,
                "difficulty": q.difficulty.value,
                "tags": [t.value for t in q.tags],
                "version": q.version,
                "validation_status": q.validation_status.value,
                "provenance": q.provenance,
            }
            for q in sorted(questions, key=lambda q: q.question_id)
        ]
        self._write_json(campaign_dir / "questions.json", data)

    def _write_ground_truth(self, campaign_dir: Path, records: list[CanonicalExecutionRecord]) -> None:
        ground_truth: dict[str, Any] = {}
        for record in records:
            qid = record.question.id
            if qid in ground_truth:
                continue
            ground_truth[qid] = {
                "scenario": record.execution.scenario,
                **record.ground_truth.model_dump(mode="json"),
            }
        self._write_json(campaign_dir / "ground_truth.json", dict(sorted(ground_truth.items())))

    def _write_executions_jsonl(self, campaign_dir: Path, records: list[CanonicalExecutionRecord]) -> None:
        lines = [json.dumps(r.model_dump(mode="json"), sort_keys=True) for r in records]
        (campaign_dir / "executions.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _write_results_json(self, campaign_dir: Path, campaign_id: str, isa95_level: str, records: list[CanonicalExecutionRecord]) -> None:
        data = {
            "campaign_id": campaign_id,
            "isa95_level": isa95_level,
            "n_executions": len(records),
            "executions": [r.model_dump(mode="json") for r in records],
        }
        self._write_json(campaign_dir / "results.json", data)

    def _write_results_csv(self, campaign_dir: Path, campaign_id: str, isa95_level: str, records: list[CanonicalExecutionRecord]) -> None:
        with (campaign_dir / "results.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=RESULTS_CSV_COLUMNS)
            writer.writeheader()
            for r in records:
                writer.writerow(
                    {
                        "execution_id": r.execution_id,
                        "campaign_id": campaign_id,
                        "isa95_level": isa95_level,
                        "question_id": r.question.id,
                        "question_text": r.question.text or "",
                        "use_case": r.question.use_case or "",
                        "category": r.question.category or "",
                        "repetition": r.execution.repetition if r.execution.repetition is not None else "",
                        "repetition_mode": r.execution.repetition_mode or "",
                        "scenario": r.execution.scenario,
                        "architecture": r.execution.architecture,
                        "agent": r.llm.agent,
                        "model": r.llm.model or "",
                        "llm_answer": r.llm.answer or "",
                        "ground_truth_answer": r.ground_truth.answer or "",
                        "expected_answer_type": r.question.expected_answer_type or "",
                        "correct": r.evaluation.correct if r.evaluation.correct is not None else "",
                        "answer_score": r.evaluation.answer_score if r.evaluation.answer_score is not None else "",
                        "evidence_score": r.evaluation.evidence_score if r.evaluation.evidence_score is not None else "",
                        "canonical_id_score": r.evaluation.canonical_id_score if r.evaluation.canonical_id_score is not None else "",
                        "failure_mode": r.evaluation.failure_mode or "",
                        "latency_ms": r.execution.latency_ms if r.execution.latency_ms is not None else "",
                        "success": r.execution.success,
                    }
                )

    def _write_per_execution_files(self, qa_dir: Path, traces_dir: Path, records: list[CanonicalExecutionRecord]) -> None:
        for r in records:
            qa_json_path = qa_dir / f"{r.execution_id}.json"
            if not qa_json_path.exists():
                self._write_json(qa_json_path, r.model_dump(mode="json"))
                (qa_dir / f"{r.execution_id}.md").write_text(_render_qa_markdown(r), encoding="utf-8")

            trace_path = traces_dir / f"{r.execution_id}.json"
            if not trace_path.exists():
                self._write_json(trace_path, r.trace.model_dump(mode="json"))

    def _write_manifest(
        self,
        campaign_dir: Path,
        isa95_level: str,
        campaign_id: str,
        records: list[CanonicalExecutionRecord],
        planned_questions: list[Question],
        manifest_extra: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = {
            "campaign_id": campaign_id,
            "isa95_level": isa95_level,
            "output_schema_version": EXPORT_SCHEMA_VERSION,
            "n_planned_questions": len(planned_questions),
            "planned_question_ids": sorted(q.question_id for q in planned_questions),
            "n_executions_exported": len(records),
            **manifest_extra,
        }
        self._write_json(campaign_dir / "benchmark_manifest.json", manifest)
        return manifest

    def _write_readme(
        self,
        campaign_dir: Path,
        isa95_level: str,
        campaign_id: str,
        records: list[CanonicalExecutionRecord],
        manifest: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        (campaign_dir / "README.md").write_text(
            _render_readme(isa95_level=isa95_level, campaign_id=campaign_id, records=records, manifest=manifest, metrics=metrics),
            encoding="utf-8",
        )


def _render_qa_markdown(r: CanonicalExecutionRecord) -> str:
    gt = r.ground_truth
    lines = [
        f"# {r.execution_id}",
        "",
        f"**ISA-95 level:** {r.isa95.level}",
        "",
        "## Question",
        "",
        f"- **ID:** {r.question.id}",
        f"- **Text:** {r.question.text or '(unavailable)'}",
        f"- **Use case:** {r.question.use_case or 'n/a'}",
        f"- **Category:** {r.question.category or 'n/a'}",
        f"- **Difficulty:** {r.question.difficulty or 'n/a'}",
        "",
        "## Ground truth",
        "",
        f"- **Answer:** {gt.answer or '(unavailable)'}",
    ]
    if gt.limitation:
        lines.append(f"- **Limitation:** {gt.limitation}")
    if gt.root_cause_disturbance:
        lines.append(f"- **Root cause disturbance:** `{gt.root_cause_disturbance}`")
    if gt.affected_measurements:
        lines.append(f"- **Affected measurements:** {', '.join(gt.affected_measurements)}")
    if gt.affected_equipment:
        lines.append(f"- **Affected equipment:** {', '.join(gt.affected_equipment)}")
    if gt.expected_relationships:
        lines.append(f"- **Expected relationships:** {'; '.join(gt.expected_relationships)}")
    if gt.expected_evidence:
        lines.append(f"- **Expected evidence:** {', '.join(gt.expected_evidence)}")

    lines += [
        "",
        "## LLM answer",
        "",
        r.llm.answer or "(no answer -- run did not complete)",
        "",
        "## Evaluation",
        "",
        f"- **Correct:** {r.evaluation.correct if r.evaluation.correct is not None else 'unavailable'}",
        f"- **Answer score:** {r.evaluation.answer_score if r.evaluation.answer_score is not None else 'n/a'}",
        f"- **Evidence score:** {r.evaluation.evidence_score if r.evaluation.evidence_score is not None else 'n/a'}",
        f"- **Canonical id score:** {r.evaluation.canonical_id_score if r.evaluation.canonical_id_score is not None else 'n/a'}",
        f"- **Failure mode:** {r.evaluation.failure_mode or 'none'}",
        "",
        "## Context",
        "",
        f"- **Available (architecture-provided):** {', '.join(r.context.available_dimensions) or 'none'}",
        f"- **Acquired (this trace):** {', '.join(r.context.context_acquired) or 'none'}",
        f"- **Consumed (discovery->retrieval hand-offs):** {', '.join(r.context.context_consumed) or 'none'}",
        "",
        "## Evidence",
        "",
        f"- **Items cited:** {', '.join(r.evidence.items) or 'none'}",
        f"- **Sources:** {', '.join(r.evidence.sources) or 'none'}",
        "",
        "## Execution",
        "",
        f"- **Repetition:** {r.execution.repetition} (mode: {r.execution.repetition_mode or 'n/a'})",
        f"- **Scenario:** {r.execution.scenario}",
        f"- **Architecture:** {r.execution.architecture}",
        f"- **Agent / model:** {r.llm.agent} / {r.llm.model or 'n/a'}",
        f"- **Latency (ms):** {r.execution.latency_ms if r.execution.latency_ms is not None else 'n/a'}",
        f"- **Success:** {r.execution.success}",
        "",
        "## Trace summary",
        "",
        f"- **Tool calls:** {len(r.trace.tool_calls)}",
        f"- **Retrieval events:** {len(r.trace.retrievals)}",
        f"- **Errors:** {'; '.join(r.trace.errors) if r.trace.errors else 'none'}",
        "",
    ]
    return "\n".join(lines)


def _render_readme(
    *,
    isa95_level: str,
    campaign_id: str,
    records: list[CanonicalExecutionRecord],
    manifest: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    return f"""# ICAB benchmark export -- {isa95_level} / {campaign_id}

This directory is a SELF-CONTAINED dataset. You do not need to install
or import ICAB (the `icab` Python package) to read or analyze it --
every file here is plain JSON, JSONL, or CSV.

## What this is

One ISA-95-level benchmark campaign's executions: each execution is one
LLM run answering one benchmark question, with its ground truth, the
LLM's answer, evaluation scores, the context/evidence the run had access
to, and its full tool-call trace.

- **ISA-95 level:** {isa95_level}
- **Campaign id:** {campaign_id}
- **Executions exported:** {len(records)}
- **Output schema version:** {manifest.get("output_schema_version")}

See `benchmark_manifest.json` for exactly what was run (question set,
repetitions, agent/model/architecture configuration, git commit,
environment) -- that file answers "what exactly was run to generate this
dataset?" in full.

## Files

| File | Contents |
|---|---|
| `benchmark_manifest.json` | What was run: config, question ids, repetitions, agent/model, git commit, environment. |
| `questions.json` | The question bank slice this campaign covers (id, text, metadata) -- independent of whether every question actually has an execution yet. |
| `ground_truth.json` | One entry per question: the correct answer and its supporting structured fields, kept separate from any LLM answer. |
| `executions.jsonl` | One canonical execution record per line (see schema below) -- the primary machine-readable dataset. |
| `results.json` | The same executions, wrapped with campaign-level metadata, as one JSON document. |
| `results.csv` | A flattened, analysis-friendly table (one row per execution) -- complex nested fields (trace, full evaluation) are NOT in the CSV; use the JSON/JSONL for those. |
| `metrics.json` | Campaign-level statistics (completion/correctness rates, per-question/use-case/category/answer-type breakdowns, repetition consistency, failure-mode counts, latency summary). |
| `q_and_a/<execution_id>.json` / `.md` | One execution's full record, `.md` human-readable. |
| `traces/<execution_id>.json` | That execution's tool-call trace alone. |

## Canonical execution record (`executions.jsonl`, `results.json`, `q_and_a/*.json`)

Each record has these top-level sections: `benchmark`, `isa95`,
`question`, `ground_truth`, `llm`, `execution`, `context`, `evidence`,
`trace`, `evaluation`. See any file under `q_and_a/` for a concrete
example, or `results.csv`'s header for the flattened column names.

## Semantics you should know before interpreting this data

- **`context.hypothesized_required_dimensions`** is a DESIGN-TIME
  hypothesis about what a question needs -- it is NOT an empirically
  demonstrated requirement. Whether a dimension was actually necessary
  is an analysis question this dataset can support, not one it answers
  for you.
- **`context.context_acquired`** vs **`context.context_consumed`**:
  `context_acquired` is what the trace's tool calls individually learned
  about; `context_consumed` is discovery -> retrieval hand-offs ONLY --
  it does NOT mean the final answer actually used that evidence. Neither
  field is the same as `evidence.items` (what the conclusion actually
  cites).
- **`execution.success`** (the run completed without error) is NOT the
  same as **`evaluation.correct`** (the answer was judged correct).
  A run can succeed and still be marked incorrect, or fail before any
  evaluation is possible (`evaluation.correct` is `null` in that case).
- **`evaluation.correct`** is computed by applying this execution's own
  task's binding evaluation criteria (which of the evaluator's scores
  must pass, and at what threshold) to this ONE run -- it is not a
  separate, invented pass/fail judgment.
- Any field that could not be determined is `null` -- never a fabricated
  placeholder. `llm.raw_response` is always `null`: ICAB does not
  currently persist the raw LLM provider response, only the structured
  conclusion.
- This export makes NO claim about "the minimum sufficient context" or
  "architecture X is required" -- those are independent-analysis
  conclusions to be drawn FROM this dataset, not something ICAB's
  execution/export layer asserts.

## Loading this dataset

Python (pandas)::

    import pandas as pd
    df = pd.read_json("executions.jsonl", lines=True)
    # or, for the flattened table:
    df = pd.read_csv("results.csv")

R::

    library(jsonlite)
    df <- stream_in(file("executions.jsonl"))

## Summary (see `metrics.json` for the full breakdown)

- Total executions exported: {metrics.get("total_executions")}
- Completed / failed: {metrics.get("completed_executions")} / {metrics.get("failed_executions")}
- Completion rate: {metrics.get("completion_rate")}
- Correctness rate (of scored executions): {metrics.get("correctness_rate")}
"""
