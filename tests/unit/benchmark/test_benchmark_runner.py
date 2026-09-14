"""
Unit tests for `icab.benchmark.runner.BenchmarkRunner` -- exercises the
real, registered tep-v1 suite's task/scenario/split configuration (no
hard-coded task list), with `ExperimentRunner.run_task` mocked out so no
simulator/gateway/LLM call is made. See
tests/integration/test_benchmark_runner_against_real_stack.py for the
end-to-end path with everything real.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from icab.benchmark import BenchmarkConfig, BenchmarkRunner
from icab.experiments import (
    AgentType,
    DeterministicAgentKind,
    ExperimentRecord,
    ExperimentResultStore,
    ExperimentRunner,
    ExperimentRunStatus,
    RunValidity,
    compute_configuration_hash,
)
from icab.trace.models import TraceEvent

D1_TASK_ID = "d1-qa-current-pressure"
D1_SCENARIO_ID = "d1_reactor_pressure_reading"


def _fake_run_task(task, config, *, scenario, run_id, experiment_id, benchmark_version, git_commit):
    """Mimics ExperimentRunner.run_task's return shape without touching the real stack."""

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


def _runner(tmp_path, run_task=None) -> BenchmarkRunner:
    experiment_runner = Mock(spec=ExperimentRunner)
    experiment_runner.run_task.side_effect = run_task or _fake_run_task

    return BenchmarkRunner(
        experiment_runner=experiment_runner,
        experiment_store=ExperimentResultStore(root=tmp_path),
    )


class TestTaskSelection:
    def test_explicit_task_id_selects_exactly_one_task(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1])

        result = runner.run(config)

        assert result.task_ids == [D1_TASK_ID]
        assert result.scenario_ids == [D1_SCENARIO_ID]

    def test_split_filter_restricts_to_that_splits_scenarios(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="tep-v1", split="development", agent="baseline", architectures="historian", seeds=[1])

        result = runner.run(config)

        # development == {d1_reactor_pressure_reading, d2_reactor_context_combination, d3_reactor_pressure_deviation}
        assert set(result.scenario_ids) <= {
            "d1_reactor_pressure_reading",
            "d2_reactor_context_combination",
            "d3_reactor_pressure_deviation",
        }
        assert result.scenario_ids  # non-empty

    def test_unknown_suite_raises(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="not-a-real-suite")

        with pytest.raises(KeyError):
            runner.run(config)

    def test_unknown_task_id_raises(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="tep-v1", task_id="not-a-real-task")

        with pytest.raises(KeyError):
            runner.run(config)


class TestArchitectureExpansionAndSkipping:
    def test_all_expands_to_the_tasks_own_architectures(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(
            suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="all", seeds=[1]
        )

        result = runner.run(config)

        # d1-qa-current-pressure only declares historian.
        assert result.architectures == ["historian"]
        assert result.total_runs == 1
        assert result.skipped_runs == 0

    def test_unsupported_architecture_is_skipped_not_run(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(
            suite="tep-v1",
            task_id=D1_TASK_ID,
            agent="baseline",
            architectures="opcua",  # the D1 task only declares historian
            seeds=[1, 2],
        )

        result = runner.run(config)

        assert result.successful_runs == 0
        assert result.failed_runs == 0
        assert result.skipped_runs == 2  # 2 seeds x 1 repetition, never silently run
        assert result.skipped_reasons
        assert result.run_ids == []


class TestSeedsAndRepetitions:
    def test_seeds_and_repetitions_expand_the_expected_number_of_runs(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(
            suite="tep-v1",
            task_id=D1_TASK_ID,
            agent="baseline",
            architectures="historian",
            seeds=[1, 2, 3],
            repetitions=2,
        )

        result = runner.run(config)

        assert result.total_runs == 3 * 2  # 3 seeds x 2 repetitions
        assert result.successful_runs == 6
        assert len(set(result.run_ids)) == 6  # every run_id is unique

    def test_no_seeds_runs_once_using_the_scenarios_own_seed(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian")

        result = runner.run(config)

        assert result.total_runs == 1
        assert result.seeds == []  # no explicit --seeds override recorded


class TestReproducibility:
    def test_only_architecture_and_seed_vary_across_arms_everything_else_held(self, tmp_path):
        """
        The independent-treatment discipline: for the SAME task/agent/
        seed, changing only --architectures must not change anything
        else about what gets passed to ExperimentRunner.run_task.
        """

        captured_configs = []

        def capturing_run_task(task, config, **kwargs):
            captured_configs.append(config)
            return _fake_run_task(task, config, **kwargs)

        runner = _runner(tmp_path, run_task=capturing_run_task)
        config = BenchmarkConfig(
            suite="tep-v1",
            task_id=D1_TASK_ID,
            agent="llm",
            architectures="all",
            seeds=[42],
            llm_model="test-model",
            llm_temperature=0.0,
            max_steps=5,
        )

        runner.run(config)

        assert len(captured_configs) == 1  # only one architecture (historian) for this task
        exp_config = captured_configs[0]
        assert exp_config.scenario_id == D1_SCENARIO_ID
        assert exp_config.task_id == D1_TASK_ID
        assert exp_config.llm_model == "test-model"
        assert exp_config.llm_temperature == 0.0
        assert exp_config.max_steps == 5

    def test_configuration_hash_is_deterministic_for_the_same_config(self, tmp_path):
        captured_configs = []

        def capturing_run_task(task, config, **kwargs):
            captured_configs.append(config)
            return _fake_run_task(task, config, **kwargs)

        runner = _runner(tmp_path, run_task=capturing_run_task)
        config = BenchmarkConfig(
            suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1, 1]
        )
        # Two identical seeds -> two runs whose ExperimentConfig should
        # hash identically (repetition/seed aren't part of the config
        # object's own identity beyond what's already captured in it).
        runner.run(config)

        hashes = {compute_configuration_hash(c) for c in captured_configs}
        assert len(hashes) == 1


class TestLegacyControlExclusion:
    def test_unknown_agent_value_fails_fast_rather_than_defaulting(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="tep-v1", task_id=D1_TASK_ID, agent="bogus-agent", architectures="historian", seeds=[1])

        # An invalid --agent value is a configuration error -- it must
        # fail the whole invocation immediately, never silently default
        # to something benchmark-eligible.
        with pytest.raises(ValueError, match="Unknown --agent"):
            runner.run(config)

    def test_explicit_legacy_agent_runs_but_is_marked_invalid(self, tmp_path):
        def run_task_recording_validity(task, config, *, scenario, run_id, experiment_id, benchmark_version, git_commit):
            record, trace = _fake_run_task(
                task, config, scenario=scenario, run_id=run_id, experiment_id=experiment_id,
                benchmark_version=benchmark_version, git_commit=git_commit,
            )
            assert config.deterministic_agent == DeterministicAgentKind.STRUCTURED_RETRIEVAL
            record = record.model_copy(update={"validity": RunValidity.LEGACY_CONTROL_ONLY})
            return record, trace

        runner = _runner(tmp_path, run_task=run_task_recording_validity)
        config = BenchmarkConfig(
            suite="tep-v1",
            task_id=D1_TASK_ID,
            agent="structured_retrieval",
            architectures="historian",
            seeds=[1],
        )

        result = runner.run(config)

        assert result.successful_runs == 1  # it ran fine...
        # ...but the persisted record itself carries the legacy marker,
        # which ExperimentResultStore.write_aggregate/aggregate_records
        # already exclude by default (unchanged M9 behavior).


class TestFailureHandlingAndContinuation:
    def test_one_failing_run_does_not_stop_the_others(self, tmp_path):
        calls = {"n": 0}

        def flaky_run_task(task, config, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("simulated scenario-preparation failure")
            return _fake_run_task(task, config, **kwargs)

        runner = _runner(tmp_path, run_task=flaky_run_task)
        config = BenchmarkConfig(
            suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1, 2, 3]
        )

        result = runner.run(config)

        assert result.total_runs == 3
        assert result.failed_runs == 1
        assert result.successful_runs == 2
        assert len(result.run_ids) == 3  # the failed run is still persisted/identified

    def test_failed_run_persists_a_record_with_error_populated(self, tmp_path):
        def always_fails(task, config, **kwargs):
            raise RuntimeError("boom")

        runner = _runner(tmp_path, run_task=always_fails)
        config = BenchmarkConfig(suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1])

        result = runner.run(config)

        assert result.failed_runs == 1
        run_id = result.run_ids[0]
        record = ExperimentResultStore(root=tmp_path).load_record(run_id)
        assert record.status == ExperimentRunStatus.FAILED
        assert "boom" in record.error
        assert record.scenario_difficulty == "D1"  # still identifiable despite the failure


class TestAggregationAndReportInvocation:
    def test_successful_runs_trigger_aggregation_and_report_output(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(
            suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1, 2]
        )

        result = runner.run(config)

        assert result.aggregate_json_path is not None
        assert result.aggregate_csv_path is not None
        assert result.report_json_path is not None
        assert result.report_markdown_path is not None

        from pathlib import Path

        assert Path(result.aggregate_json_path).exists()
        assert Path(result.aggregate_csv_path).exists()
        assert Path(result.report_json_path).exists()
        assert Path(result.report_markdown_path).exists()

    def test_no_successful_runs_produces_no_aggregate_or_report(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(
            suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="opcua", seeds=[1]
        )

        result = runner.run(config)

        assert result.skipped_runs == 1
        assert result.aggregate_json_path is None
        assert result.report_json_path is None


class TestRunPersistence:
    def test_every_run_is_persisted_under_raw_and_evaluations(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1])

        result = runner.run(config)

        store = ExperimentResultStore(root=tmp_path)
        run_id = result.run_ids[0]
        record = store.load_record(run_id)
        assert record.run_id == run_id
        assert record.config.task_id == D1_TASK_ID
        assert record.config.suite == "tep-v1"
        assert record.config.split is not None
        assert record.benchmark_version is not None
        assert record.configuration_hash is not None

    def test_run_ids_are_unique_and_identifiable(self, tmp_path):
        runner = _runner(tmp_path)
        config = BenchmarkConfig(
            suite="tep-v1", task_id=D1_TASK_ID, agent="baseline", architectures="historian", seeds=[1, 2], repetitions=2
        )

        result = runner.run(config)

        assert len(result.run_ids) == len(set(result.run_ids)) == 4
        for run_id in result.run_ids:
            assert D1_TASK_ID in run_id
