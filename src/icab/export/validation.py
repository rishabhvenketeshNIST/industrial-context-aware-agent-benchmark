"""
Standalone integrity checks over an already-written campaign export
directory (`benchmark_exports/<level>/<campaign_id>/`) -- reads ONLY the
plain JSON/JSONL/CSV files a campaign export writes (never ICAB's
internal `results/` store), proving the export is genuinely self-
contained: these checks would catch the same problems an external
analyst who has never opened the ICAB repo would hit.

Fails loudly: `ExportValidationReport.is_valid` is False whenever ANY
issue is found -- never silently reports a partial/corrupted export as
complete.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ExportValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_dir: str
    n_executions: int
    issues: list[str] = []

    @property
    def is_valid(self) -> bool:
        return not self.issues


def validate_export(campaign_dir: str | Path) -> ExportValidationReport:
    campaign_dir = Path(campaign_dir)
    issues: list[str] = []

    required_files = ("README.md", "benchmark_manifest.json", "questions.json", "ground_truth.json", "executions.jsonl", "results.json", "results.csv", "metrics.json")
    for name in required_files:
        if not (campaign_dir / name).exists():
            issues.append(f"missing required file: {name}")

    if issues:
        # Nothing further can be checked without the core files.
        return ExportValidationReport(campaign_dir=str(campaign_dir), n_executions=0, issues=issues)

    manifest = json.loads((campaign_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
    isa95_level = manifest.get("isa95_level")

    jsonl_lines = [
        json.loads(line) for line in (campaign_dir / "executions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    results_json = json.loads((campaign_dir / "results.json").read_text(encoding="utf-8"))
    results_executions = results_json.get("executions", [])

    execution_ids = [r.get("execution_id") for r in jsonl_lines]
    duplicate_ids = {eid for eid in execution_ids if execution_ids.count(eid) > 1}
    if duplicate_ids:
        issues.append(f"duplicate execution_id(s) in executions.jsonl: {sorted(duplicate_ids)}")

    if len(jsonl_lines) != len(results_executions):
        issues.append(f"executions.jsonl has {len(jsonl_lines)} record(s) but results.json has {len(results_executions)}")

    if manifest.get("n_executions_exported") != len(jsonl_lines):
        issues.append(
            f"benchmark_manifest.json n_executions_exported={manifest.get('n_executions_exported')} disagrees "
            f"with executions.jsonl's {len(jsonl_lines)} record(s)"
        )

    with (campaign_dir / "results.csv").open("r", newline="", encoding="utf-8") as file:
        import csv

        csv_rows = list(csv.DictReader(file))
    if len(csv_rows) != len(jsonl_lines):
        issues.append(f"results.csv has {len(csv_rows)} row(s) but executions.jsonl has {len(jsonl_lines)}")

    mismatched_level = [r["execution_id"] for r in jsonl_lines if r.get("isa95", {}).get("level") != isa95_level]
    if mismatched_level:
        issues.append(f"{len(mismatched_level)} execution(s) have isa95.level != campaign level {isa95_level!r}: {mismatched_level[:5]}")

    seen_question_repetition: dict[tuple, int] = {}
    for record in jsonl_lines:
        key = (record.get("question", {}).get("id"), record.get("execution", {}).get("repetition"))
        seen_question_repetition[key] = seen_question_repetition.get(key, 0) + 1
    duplicate_pairs = [key for key, count in seen_question_repetition.items() if count > 1]
    if duplicate_pairs:
        issues.append(f"duplicate (question_id, repetition) execution(s): {duplicate_pairs[:5]}")

    for record in jsonl_lines:
        eid = record.get("execution_id")
        for subdir, suffix in (("q_and_a", ".json"), ("traces", ".json")):
            path = campaign_dir / subdir / f"{eid}{suffix}"
            if not path.exists():
                issues.append(f"missing {subdir}/{eid}{suffix} for execution {eid}")

    ground_truth = json.loads((campaign_dir / "ground_truth.json").read_text(encoding="utf-8"))
    question_ids = {r.get("question", {}).get("id") for r in jsonl_lines}
    missing_ground_truth = [qid for qid in question_ids if qid not in ground_truth or ground_truth[qid].get("limitation")]
    if missing_ground_truth:
        issues.append(f"{len(missing_ground_truth)} question(s) executed with no usable ground truth recorded: {sorted(missing_ground_truth)[:5]}")

    return ExportValidationReport(campaign_dir=str(campaign_dir), n_executions=len(jsonl_lines), issues=issues)
