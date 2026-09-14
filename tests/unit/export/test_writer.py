"""
Unit tests for `icab.export.writer.CampaignExportWriter` -- exercises the
full standalone export directory it produces, and that a written export
is genuinely parseable with PLAIN `json`/`csv` (no ICAB import) as an
external analyst would.
"""

from __future__ import annotations

import csv
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


def _registries():
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(QUESTIONS_DIR, use_case_registry=use_case_registry, task_registry=task_registry)
    return question_registry, task_registry


def _canonical_records(n: int):
    question_registry, task_registry = _registries()
    question = question_registry.get(QUESTION_ID)
    task = task_registry.get(TASK_ID)

    records = []
    for i in range(1, n + 1):
        record = make_record(f"run-{i}", repetition=i, evaluation=make_evaluation())
        records.append(
            build_canonical_record(
                record, make_trace(), question=question, task=task, campaign_id="campaign-x", benchmark_name="icab-equipment-v1", benchmark_version="1.0.0"
            )
        )
    return records, [question]


class TestWriteProducesEveryRequiredFile:
    def test_write_produces_the_full_export_tree(self, tmp_path):
        records, questions = _canonical_records(3)
        writer = CampaignExportWriter(output_root=tmp_path)

        campaign_dir = writer.write(
            isa95_level="equipment", campaign_id="campaign-x", records=records, planned_questions=questions, manifest_extra={"repetitions": 3}
        )

        for name in ("README.md", "benchmark_manifest.json", "questions.json", "ground_truth.json", "executions.jsonl", "results.json", "results.csv", "metrics.json"):
            assert (campaign_dir / name).exists(), name

        for record in records:
            assert (campaign_dir / "q_and_a" / f"{record.execution_id}.json").exists()
            assert (campaign_dir / "q_and_a" / f"{record.execution_id}.md").exists()
            assert (campaign_dir / "traces" / f"{record.execution_id}.json").exists()

    def test_export_root_is_separate_from_results(self, tmp_path):
        records, questions = _canonical_records(1)
        writer = CampaignExportWriter(output_root=tmp_path / "benchmark_exports")
        campaign_dir = writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=questions, manifest_extra={})

        assert "benchmark_exports" in str(campaign_dir)
        assert "results" not in campaign_dir.relative_to(tmp_path).parts


class TestStandaloneParseability:
    def test_executions_jsonl_is_parseable_with_plain_json_no_icab_import(self, tmp_path):
        records, questions = _canonical_records(2)
        writer = CampaignExportWriter(output_root=tmp_path)
        campaign_dir = writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=questions, manifest_extra={})

        lines = (campaign_dir / "executions.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert all("execution_id" in p and "question" in p and "ground_truth" in p and "evaluation" in p for p in parsed)

    def test_results_csv_has_the_documented_columns_and_no_nested_json(self, tmp_path):
        records, questions = _canonical_records(2)
        writer = CampaignExportWriter(output_root=tmp_path)
        campaign_dir = writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=questions, manifest_extra={})

        with (campaign_dir / "results.csv").open(encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 2
        for column in ("execution_id", "question_id", "llm_answer", "ground_truth_answer", "correct", "answer_score", "failure_mode", "latency_ms"):
            assert column in rows[0]
        assert "{" not in rows[0]["llm_answer"]  # no accidental JSON dump leaking into a flat cell


class TestImmutabilityAcrossResumedWrites:
    def test_writing_again_with_more_records_never_rewrites_an_existing_per_execution_file(self, tmp_path):
        records, questions = _canonical_records(2)
        writer = CampaignExportWriter(output_root=tmp_path)
        campaign_dir = writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=questions, manifest_extra={})

        first_path = campaign_dir / "q_and_a" / f"{records[0].execution_id}.json"
        original_bytes = first_path.read_bytes()
        original_mtime = first_path.stat().st_mtime_ns

        more_records, _ = _canonical_records(4)  # includes the same run-1/run-2 plus 2 new
        writer.write(isa95_level="equipment", campaign_id="c", records=more_records, planned_questions=questions, manifest_extra={})

        assert first_path.read_bytes() == original_bytes
        assert first_path.stat().st_mtime_ns == original_mtime
        assert (campaign_dir / "q_and_a" / f"{more_records[-1].execution_id}.json").exists()

    def test_aggregate_files_are_regenerated_to_reflect_every_record_so_far(self, tmp_path):
        records, questions = _canonical_records(1)
        writer = CampaignExportWriter(output_root=tmp_path)
        campaign_dir = writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=questions, manifest_extra={})

        more_records, _ = _canonical_records(3)
        writer.write(isa95_level="equipment", campaign_id="c", records=more_records, planned_questions=questions, manifest_extra={})

        lines = (campaign_dir / "executions.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        manifest = json.loads((campaign_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
        assert manifest["n_executions_exported"] == 3


class TestValidateExportOnAWrittenCampaign:
    def test_a_freshly_written_export_validates_clean(self, tmp_path):
        records, questions = _canonical_records(5)
        writer = CampaignExportWriter(output_root=tmp_path)
        campaign_dir = writer.write(isa95_level="equipment", campaign_id="c", records=records, planned_questions=questions, manifest_extra={})

        report = validate_export(campaign_dir)
        assert report.is_valid, report.issues
        assert report.n_executions == 5

    def test_a_directory_missing_required_files_fails_validation(self, tmp_path):
        (tmp_path / "empty_dir").mkdir()
        report = validate_export(tmp_path / "empty_dir")
        assert not report.is_valid
        assert any("missing required file" in issue for issue in report.issues)
