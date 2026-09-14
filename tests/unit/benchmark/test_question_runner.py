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


class TestPlan:
    def test_plan_makes_no_run_task_call_and_persists_nothing(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True, repetitions=7)

        plan = runner.plan(config)

        runner.experiment_runner.run_task.assert_not_called()
        assert ExperimentResultStore(root=tmp_path).list_run_ids() == []
        assert plan.isa95_level == "equipment"
        assert plan.planned_instances == 1
        assert plan.planned_executions == 7  # 1 instance x 7 repetitions x 1 (default) seed
        assert plan.outcomes[0].question_id == EQUIPMENT_QUESTION_ID
        assert plan.outcomes[0].instance_id is not None

    def test_plan_reflects_the_same_resolution_as_a_real_run(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True, repetitions=2)

        plan = runner.plan(config)
        result = runner.run(config)

        assert plan.outcomes[0].instance_id == result.outcomes[0].instance_id
        assert plan.outcomes[0].resolved_architectures == result.outcomes[0].resolved_architectures


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


class TestResume:
    def test_resume_continues_a_started_campaign_without_a_collision_error(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(
            question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True, repetitions=2, name="resume-campaign"
        )

        runner.run(config)  # first invocation: 2 runs

        # A second, non-resume invocation of the SAME name still collides.
        with pytest.raises(BenchmarkIdCollisionError):
            runner.run(config)

        resumed = config.model_copy(update={"resume": True})
        result = runner.run(resumed)  # does not raise

        assert result.total_runs == 2  # both repetitions accounted for, none duplicated

    def test_resume_never_re_executes_an_already_completed_run_id(self, tmp_path):
        call_count = {"n": 0}

        def _counting_run_task(task, config, *, scenario, run_id, experiment_id, benchmark_version, git_commit):
            call_count["n"] += 1
            return _fake_run_task(task, config, scenario=scenario, run_id=run_id, experiment_id=experiment_id, benchmark_version=benchmark_version, git_commit=git_commit)

        runner = _runner(tmp_path, ISA95Level.EQUIPMENT, run_task=_counting_run_task)
        config = QuestionBenchmarkConfig(
            question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True, repetitions=3, name="resume-count-campaign"
        )
        runner.run(config)
        assert call_count["n"] == 3

        resumed = config.model_copy(update={"resume": True})
        result = runner.run(resumed)

        # No NEW execution() calls -- every (instance, seed, repetition) run_id
        # from the first invocation already existed, so resume only reads them back.
        assert call_count["n"] == 3
        assert result.total_runs == 3

    def test_resume_picks_up_where_a_partial_campaign_left_off(self, tmp_path):
        runner = _runner(tmp_path, ISA95Level.EQUIPMENT)
        config = QuestionBenchmarkConfig(
            question_ids=[EQUIPMENT_QUESTION_ID], agent="baseline", allow_overshoot=True, repetitions=2, name="partial-campaign"
        )
        runner.run(config)  # 2/2 repetitions done

        more_repetitions = config.model_copy(update={"repetitions": 5, "resume": True})
        result = runner.run(more_repetitions)

        # Repetitions 1-2 skipped (already persisted), 3-5 newly executed --
        # total_runs reflects the FULL, now-5-repetition campaign.
        assert result.total_runs == 5
        run_ids = result.outcomes[0].run_ids
        assert len(run_ids) == 5
        assert len(set(run_ids)) == 5  # no duplicate run_ids


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
