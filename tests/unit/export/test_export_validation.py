"""
Unit tests for `icab.export.validation.validate_export` catching a
corrupted/tampered/incomplete campaign export -- must fail loudly
(non-empty `issues`), never silently report a broken export as valid.
"""

from __future__ import annotations

import json

from icab.export.build import build_canonical_record
from icab.export.validation import validate_export
from icab.export.writer import CampaignExportWriter
from icab.questions import QuestionBankRegistry
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

from _export_factories import make_evaluation, make_record, make_trace

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"
QUESTIONS_DIR = "configs/questions/equipment"

QUESTION_ID = "Q-d1-qa-current-pressure"
TASK_ID = "d1-qa-current-pressure"


def _write_clean_campaign(tmp_path, n=3):
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(QUESTIONS_DIR, use_case_registry=use_case_registry, task_registry=task_registry)
    question = question_registry.get(QUESTION_ID)
    task = task_registry.get(TASK_ID)

    records = [
        build_canonical_record(
            make_record(f"run-{i}", repetition=i, evaluation=make_evaluation()),
            make_trace(),
            question=question,
            task=task,
            campaign_id="c",
            benchmark_name="icab-equipment-v1",
            benchmark_version="1.0.0",
        )
        for i in range(1, n + 1)
    ]

    writer = CampaignExportWriter(output_root=tmp_path)
    return writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=[question], manifest_extra={})


class TestValidationCatchesCorruption:
    def test_a_tampered_duplicate_execution_id_is_caught(self, tmp_path):
        campaign_dir = _write_clean_campaign(tmp_path)
        lines = (campaign_dir / "executions.jsonl").read_text(encoding="utf-8").splitlines()
        tampered = lines + [lines[0]]  # duplicate the first record
        (campaign_dir / "executions.jsonl").write_text("\n".join(tampered) + "\n", encoding="utf-8")

        report = validate_export(campaign_dir)

        assert not report.is_valid
        assert any("duplicate execution_id" in issue for issue in report.issues)

    def test_a_manifest_count_mismatch_is_caught(self, tmp_path):
        campaign_dir = _write_clean_campaign(tmp_path)
        manifest = json.loads((campaign_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
        manifest["n_executions_exported"] = 999
        (campaign_dir / "benchmark_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        report = validate_export(campaign_dir)

        assert not report.is_valid
        assert any("n_executions_exported" in issue for issue in report.issues)

    def test_a_missing_per_execution_file_is_caught(self, tmp_path):
        campaign_dir = _write_clean_campaign(tmp_path)
        first_qa_file = next((campaign_dir / "q_and_a").glob("*.json"))
        first_qa_file.unlink()

        report = validate_export(campaign_dir)

        assert not report.is_valid
        assert any("missing q_and_a" in issue for issue in report.issues)

    def test_a_truncated_results_csv_is_caught(self, tmp_path):
        campaign_dir = _write_clean_campaign(tmp_path)
        lines = (campaign_dir / "results.csv").read_text(encoding="utf-8").splitlines()
        (campaign_dir / "results.csv").write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")  # drop rows

        report = validate_export(campaign_dir)

        assert not report.is_valid
        assert any("results.csv has" in issue for issue in report.issues)

    def test_cross_level_contamination_is_caught(self, tmp_path):
        campaign_dir = _write_clean_campaign(tmp_path)
        manifest = json.loads((campaign_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
        manifest["isa95_level"] = "process_cell"  # campaign dir says equipment, manifest now disagrees
        (campaign_dir / "benchmark_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        report = validate_export(campaign_dir)

        assert not report.is_valid
        assert any("isa95.level" in issue for issue in report.issues)
