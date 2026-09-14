"""
Unit tests for `icab.benchmark.question_runner.QuestionBenchmarkRunner` --
exercises the real, registered Equipment/Process-Cell question banks
(no hard-coded question list), with `ExperimentRunner.run_task` mocked
out so no simulator/gateway/LLM call is made.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from icab.benchmark.levels import get_level_benchmark
from icab.benchmark.question_runner import (
    IsaLevelMismatchError,
    QuestionBenchmarkConfig,
    QuestionBenchmarkRunner,
)
from icab.benchmark.runner import BenchmarkIdCollisionError
from icab.experiments import (
    ExperimentRecord,
    ExperimentResultStore,
    ExperimentRunner,
    ExperimentRunStatus,
    RunValidity,
    compute_configuration_hash,
)
from icab.questions import QuestionBankRegistry
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.isa95 import ISA95Level
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"

#: A real Equipment question realized on a real scenario -- historian only.
EQUIPMENT_QUESTION_ID = "Q-d1-qa-current-pressure"


def _fake_run_task(task, config, *, scenario, run_id, experiment_id, benchmark_version, git_commit):
    now = datetime.now(UTC)
    record = ExperimentRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        config=config,
        scenario_difficulty=task.difficulty.value,
        simulation_seed=scenario.seed,
        generation_id="fake-generation-id",
        icab_version="test",
        benchmark_version=benchmark_version,
        git_commit=git_commit,
        fault_id=scenario.faults[0].disturbance if scenario.faults else None,
        scenario_version=scenario.version,
        task_version=task.version,
        configuration_hash=compute_configuration_hash(config),
        started_at=now,
        completed_at=now,
        status=ExperimentRunStatus.COMPLETED,
        validity=RunValidity.VALID,
        result=None,
        evaluation=None,
        information_flow=None,
        trace_event_count=0,
    )
    return record, []


def _runner(tmp_path, level: ISA95Level, run_task=None) -> QuestionBenchmarkRunner:
    experiment_runner = Mock(spec=ExperimentRunner)
    experiment_runner.run_task.side_effect = run_task or _fake_run_task

    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    definition = get_level_benchmark(level)
    question_registry = QuestionBankRegistry(definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)

    return QuestionBenchmarkRunner(
        definition=definition,
        experiment_runner=experiment_runner,
        question_registry=question_registry,
        use_case_registry=use_case_registry,
        task_registry=task_registry,
        scenario_registry=scenario_registry,
        experiment_store=ExperimentResultStore(root=tmp_path),
    )


class TestQuestionSelection:
    def test_explicit_question_id_selects_exactly_one(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True)

        result = runner.run(config)

        assert {o.question_id for o in result.outcomes} == {EQUIPMENT_QUESTION_ID}

    def test_unknown_filters_match_nothing_and_raise(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=["not-a-real-question"], agent="baseline")

        with pytest.raises(ValueError, match="No questions matched"):
            runner.run(config)


class TestResultPathIsolation:
    def test_runs_are_persisted_under_the_level_scoped_store_only(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True)

        result = runner.run(config)

        store = ExperimentResultStore(root=tmp_path)
        run_ids = [rid for outcome in result.outcomes for rid in outcome.run_ids]
        assert run_ids
        for run_id in run_ids:
            record = store.load_record(run_id)
            assert record.config.isa95_level == "equipment"
            assert record.config.question_id == EQUIPMENT_QUESTION_ID
            assert record.config.question_instance_id is not None

    def test_manifest_is_written_under_the_experiment_store_root_not_the_real_results_tree(self, tmp_path):
        # Regression: write_manifest's own default root is
        # definition.results_root (the REAL production results/<level>/
        # tree) -- QuestionBenchmarkRunner must always pass
        # root=self.experiment_store.root explicitly, or a test/alternate
        # store would silently leak a manifest.json into the real
        # results/ directory.
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True)

        result = runner.run(config)

        from pathlib import Path

        assert result.manifest_path is not None
        manifest_path = Path(result.manifest_path).resolve()
        assert manifest_path.is_relative_to(tmp_path.resolve())

        real_results_root = Path("results") / "equipment" / "manifest.json"
        assert not real_results_root.exists() or real_results_root.resolve() != manifest_path

    def test_manifest_is_written_and_traceable(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True)

        result = runner.run(config)

        assert result.manifest_path is not None
        import json

        manifest = json.loads(open(result.manifest_path, encoding="utf-8").read())
        assert manifest["isa95_level"] == "equipment"
        assert manifest["n_questions"] >= 1
        assert set(manifest["run_ids"]) >= set(rid for outcome in result.outcomes for rid in outcome.run_ids)


class TestIsaLevelMismatchGuard:
    def test_a_run_whose_config_disagrees_with_the_benchmark_level_fails_loudly(self, tmp_path):
        def _wrong_level_run_task(task, config, *, scenario, run_id, experiment_id, benchmark_version, git_commit):
            record, trace = _fake_run_task(task, config, scenario=scenario, run_id=run_id, experiment_id=experiment_id, benchmark_version=benchmark_version, git_commit=git_commit)
            # Simulate a corrupted/mismatched config sneaking through --
            # this must be caught, not silently persisted.
            bad_config = record.config.model_copy(update={"isa95_level": "process_cell"})
            record = record.model_copy(update={"config": bad_config})
            return record, trace

        runner = _runner(tmp_path, ISA95Level.EQUIPMENT, run_task=_wrong_level_run_task)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True)

        with pytest.raises(IsaLevelMismatchError):
            runner.run(config)


class TestNotExecutableLevelsRefuseConstruction:
    def test_a_non_executable_definition_refuses_to_even_construct_a_runner(self, tmp_path):
        # ICAB v3's 50-question milestone made all SIX real levels
        # executable (see docs/benchmark/specification-v3.md) -- so this
        # exercises the guard mechanism itself via a synthetic,
        # non-executable definition rather than relying on any one real
        # level staying unsupported forever.
        import dataclasses

        experiment_runner = Mock(spec=ExperimentRunner)
        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
        use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
        real_definition = get_level_benchmark(ISA95Level.ENTERPRISE)
        not_executable = dataclasses.replace(real_definition, executable=False, data_supported=False)
        question_registry = QuestionBankRegistry(real_definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)

        with pytest.raises(ValueError, match="not executable"):
            QuestionBenchmarkRunner(
                definition=not_executable,
                experiment_runner=experiment_runner,
                question_registry=question_registry,
                use_case_registry=use_case_registry,
                task_registry=task_registry,
                scenario_registry=scenario_registry,
                experiment_store=ExperimentResultStore(root=tmp_path),
            )


class TestCampaignIdCollision:
    def test_reusing_an_explicit_name_is_refused(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True, name="fixed-campaign")

        runner.run(config)
        with pytest.raises(BenchmarkIdCollisionError):
            runner.run(config)

        forced = config.model_copy(update={"force": True})
        runner.run(forced)  # does not raise


class TestRepetitions:
    def test_repetitions_are_not_hard_coded_and_produce_that_many_runs(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", repetitions=4, allow_overshoot=True)

        result = runner.run(config)

        assert result.total_runs == 4
        assert result.successful_runs == 4
        assert result.failed_runs == 0

    def test_repetition_mode_is_recorded_on_every_run(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", repetition_mode="controlled_variation", allow_overshoot=True)

        result = runner.run(config)

        store = ExperimentResultStore(root=tmp_path)
        run_id = result.outcomes[0].run_ids[0]
        record = store.load_record(run_id)
        assert record.config.repetition_mode == "controlled_variation"
