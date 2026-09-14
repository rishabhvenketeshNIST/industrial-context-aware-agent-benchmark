"""
Unit tests for `icab.benchmark.context_experiment.ContextExperimentRunner`
-- exercises the real, registered tep-v2 suite's task/use-case
configuration (no hard-coded task list), with `ExperimentRunner.run_task`
mocked out so no simulator/gateway/LLM call is made. See
tests/integration/test_context_experiment_against_real_stack.py for the
end-to-end path with everything real.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from icab.benchmark import (
    BenchmarkIdCollisionError,
    ContextExperimentConfig,
    ContextExperimentRunner,
)
from icab.experiments import (
    ExperimentRecord,
    ExperimentResultStore,
    ExperimentRunner,
    ExperimentRunStatus,
    RunValidity,
    compute_configuration_hash,
)
from icab.scenarios import BenchmarkScenarioRegistry
from icab.usecases import IndustrialUseCaseRegistry

#: Open-ended, multi-architecture Process Cell task -- 5 architectures
#: (historian/knowledge_graph/uns/opcua/mqtt), so single-dimension C5
#: resolves EXACT (mqtt alone), everything else in its candidate_context
#: overshoots, and C6 is outside its use case's own candidate_context.
D4_TASK_ID = "d4plant-investigation-open-ended"

#: Two-architecture (historian + knowledge_graph) Equipment task -- good
#: for ablation: its default baseline (both architectures together) is
#: EXACT by construction, and every single-dimension removal overshoots.
D2_TASK_ID = "d2cooling-diagnosis-heat-transfer-category"


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


def _runner(tmp_path, *, with_use_cases: bool = True, run_task=None) -> ContextExperimentRunner:
    experiment_runner = Mock(spec=ExperimentRunner)
    experiment_runner.run_task.side_effect = run_task or _fake_run_task

    use_case_registry = None
    if with_use_cases:
        use_case_registry = IndustrialUseCaseRegistry(
            "configs/usecases",
            scenario_registry=BenchmarkScenarioRegistry("configs/benchmark/scenarios"),
        )

    return ContextExperimentRunner(
        experiment_runner=experiment_runner,
        experiment_store=ExperimentResultStore(root=tmp_path),
        use_case_registry=use_case_registry,
    )


class TestSingleDimensionDesign:
    def test_classifies_all_seven_dimensions_correctly(self, tmp_path):
        runner = _runner(tmp_path)
        config = ContextExperimentConfig(suite="tep-v2", task_id=D4_TASK_ID, design="single", agent="baseline", seeds=[1])

        result = runner.run(config)

        assert result.total_conditions == 7
        by_id = {c.combination_id: c for c in result.conditions}

        # C5 is exactly realizable via mqtt alone.
        assert by_id["C5"].resolution_status == "exact"
        assert by_id["C5"].executed is True
        assert by_id["C5"].resolved_architectures == ["mqtt"]

        # C6 is outside pc-open-ended-abnormal-investigation's own candidate_context.
        assert by_id["C6"].resolution_status == "not_applicable"
        assert by_id["C6"].executed is False

        # Every other single dimension overshoots given these 5 architectures.
        for dim in ("C1", "C2", "C3", "C4", "C7"):
            assert by_id[dim].resolution_status == "overshoot", dim
            assert by_id[dim].executed is False  # allow_overshoot defaults to False

        assert result.executed_conditions == 1
        assert result.not_applicable_conditions == 1
        assert result.overshoot_skipped_conditions == 5
        assert result.unrealizable_conditions == 0
        assert result.total_runs == 1
        assert result.successful_runs == 1
        assert result.failed_runs == 0

    def test_not_executed_is_never_counted_as_a_failure(self, tmp_path):
        runner = _runner(tmp_path)
        config = ContextExperimentConfig(suite="tep-v2", task_id=D4_TASK_ID, design="single", agent="baseline", seeds=[1])

        result = runner.run(config)

        # 6 conditions were not executed (not_applicable + overshoot-skipped); none inflate failed_runs.
        assert result.executed_conditions + result.not_applicable_conditions + result.overshoot_skipped_conditions == result.total_conditions
        assert result.failed_runs == 0
        assert result.total_runs == result.executed_conditions  # one run each, seeds=[1] * repetitions=1

    def test_allow_overshoot_executes_every_applicable_condition(self, tmp_path):
        runner = _runner(tmp_path)
        config = ContextExperimentConfig(
            suite="tep-v2", task_id=D4_TASK_ID, design="single", agent="baseline", seeds=[1], allow_overshoot=True
        )

        result = runner.run(config)

        assert result.executed_conditions == 6  # everything except C6 (not_applicable)
        assert result.overshoot_skipped_conditions == 0
        assert result.not_applicable_conditions == 1

    def test_without_a_use_case_registry_nothing_is_not_applicable(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(suite="tep-v2", task_id=D4_TASK_ID, design="single", agent="baseline", seeds=[1])

        result = runner.run(config)

        assert result.not_applicable_conditions == 0
        # C6 is now UNREALIZABLE-or-overshoot purely by architecture, not filtered by use case.
        by_id = {c.combination_id: c for c in result.conditions}
        assert by_id["C6"].resolution_status in ("overshoot", "exact")


class TestPairwiseDesign:
    def test_generates_21_conditions(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(suite="tep-v2", task_id=D4_TASK_ID, design="pairwise", agent="baseline", seeds=[1])

        result = runner.run(config)

        assert result.total_conditions == 21


class TestAblationDesign:
    def test_default_baseline_is_exact_and_every_removal_overshoots(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(suite="tep-v2", task_id=D2_TASK_ID, design="ablation", agent="baseline", seeds=[1])

        result = runner.run(config)

        # baseline (both architectures together) + one removal per dimension it provides.
        assert result.total_conditions == 7
        baseline = result.conditions[0]
        assert baseline.resolution_status == "exact"
        assert baseline.executed is True
        assert set(baseline.resolved_architectures) == {"historian", "knowledge_graph"}

        for removal in result.conditions[1:]:
            assert removal.resolution_status == "overshoot"
            assert removal.executed is False  # allow_overshoot defaults to False

        assert result.executed_conditions == 1

    def test_allow_overshoot_runs_every_ablation_step(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(
            suite="tep-v2", task_id=D2_TASK_ID, design="ablation", agent="baseline", seeds=[1], allow_overshoot=True
        )

        result = runner.run(config)

        assert result.executed_conditions == 7
        assert result.total_runs == 7

    def test_explicit_baseline_is_used_instead_of_the_default(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(
            suite="tep-v2", task_id=D2_TASK_ID, design="ablation", baseline="C3+C6", agent="baseline", seeds=[1]
        )

        result = runner.run(config)

        assert result.conditions[0].combination_id == "C3+C6"


class TestTargetedDesign:
    def test_runs_exactly_the_named_combinations(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(
            suite="tep-v2", task_id=D4_TASK_ID, design="targeted", targets=["C5", "C2+C5"], agent="baseline", seeds=[1]
        )

        result = runner.run(config)

        assert result.total_conditions == 2
        assert {c.combination_id for c in result.conditions} == {"C5", "C2+C5"}

    def test_unknown_combination_id_raises(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(
            suite="tep-v2", task_id=D4_TASK_ID, design="targeted", targets=["not-a-real-id"], agent="baseline", seeds=[1]
        )

        with pytest.raises(KeyError):
            runner.run(config)


class TestReplayDesign:
    def test_replays_exactly_the_combinations_already_persisted_for_this_task(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)

        # First: run a single-dimension design so something is persisted for this task.
        first = runner.run(
            ContextExperimentConfig(suite="tep-v2", task_id=D4_TASK_ID, design="single", agent="baseline", seeds=[1])
        )
        assert first.executed_conditions == 1  # just C5

        replay = runner.run(
            ContextExperimentConfig(suite="tep-v2", task_id=D4_TASK_ID, design="replay", agent="baseline", seeds=[1])
        )

        assert {c.combination_id for c in replay.conditions} == {"C5"}
        assert replay.conditions[0].resolution_status == "exact"
        assert replay.conditions[0].executed is True


class TestCampaignIdCollision:
    def test_reusing_an_explicit_name_is_refused(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(
            suite="tep-v2", task_id=D4_TASK_ID, design="single", agent="baseline", seeds=[1], name="fixed-campaign"
        )

        runner.run(config)
        with pytest.raises(BenchmarkIdCollisionError):
            runner.run(config)

        # force=True overrides deliberately.
        forced = config.model_copy(update={"force": True})
        runner.run(forced)  # does not raise


class TestUnknownTask:
    def test_unknown_task_id_raises_a_clear_error(self, tmp_path):
        runner = _runner(tmp_path, with_use_cases=False)
        config = ContextExperimentConfig(suite="tep-v2", task_id="not-a-real-task", design="single", agent="baseline")

        with pytest.raises(ValueError, match="Unknown --task"):
            runner.run(config)
