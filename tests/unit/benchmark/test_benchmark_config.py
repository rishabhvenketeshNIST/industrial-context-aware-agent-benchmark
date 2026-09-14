import pytest

from icab.benchmark.config import (
    BENCHMARK_SUITE_VERSION,
    BenchmarkConfig,
    get_git_commit,
    get_suite,
    resolve_architecture_arms,
)
from icab.scenarios.models import GroundTruth, ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import BenchmarkTask, EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension


def _task(available_architectures: list[str]) -> BenchmarkTask:
    return BenchmarkTask(
        task_id="test-task",
        scenario_id="test-scenario",
        task_type=TaskMode.QA,
        difficulty=ScenarioDifficulty.D1,
        objective="What is the current reactor pressure?",
        available_architectures=available_architectures,
        required_context_dimensions=[ContextDimension.C5_OPERATIONAL],
        required_evidence=["urn:icab:measurement:reactor_pressure"],
        ground_truth=GroundTruth(conclusion="~2705 kPa gauge."),
        evaluation_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
    )


class TestGetSuite:
    def test_tep_v1_is_registered(self):
        suite = get_suite("tep-v1")
        assert suite.name == "tep-v1"
        assert suite.scenarios_dir.exists()
        assert suite.tasks_dir.exists()
        assert suite.splits_path.exists()

    def test_unknown_suite_raises(self):
        with pytest.raises(KeyError, match="Unknown benchmark suite"):
            get_suite("nonexistent-suite")


class TestResolveArchitectureArms:
    def test_all_expands_to_one_arm_per_task_architecture(self):
        task = _task(["historian", "knowledge_graph"])

        arms = resolve_architecture_arms("all", task)

        assert {arm.architectures for arm in arms} == {("historian",), ("knowledge_graph",)}
        assert all(arm.combination_key is None for arm in arms)

    def test_all_never_includes_an_architecture_the_task_does_not_declare(self):
        # The task only declares historian -- "all" must never silently
        # add i3x/opcua/mqtt/etc. just because ICAB knows how to talk to
        # them.
        task = _task(["historian"])

        arms = resolve_architecture_arms("all", task)

        assert arms == [type(arms[0])(architectures=("historian",), combination_key=None)]

    def test_named_combination_subset_of_task_architectures_resolves(self):
        task = _task(["historian", "knowledge_graph", "uns", "opcua", "mqtt"])

        arms = resolve_architecture_arms("historian_only", task)

        assert len(arms) == 1
        assert arms[0].architectures == ("historian",)
        assert arms[0].combination_key == "historian_only"

    def test_named_combination_not_subset_of_task_architectures_is_skipped(self):
        # "full" requires every architecture; a historian-only task must
        # not silently run a subset of it.
        task = _task(["historian"])

        arms = resolve_architecture_arms("full", task)

        assert arms == []

    def test_raw_comma_list_subset_resolves_as_one_arm(self):
        task = _task(["historian", "knowledge_graph", "uns"])

        arms = resolve_architecture_arms("historian,knowledge_graph", task)

        assert len(arms) == 1
        assert set(arms[0].architectures) == {"historian", "knowledge_graph"}
        assert arms[0].combination_key is None

    def test_raw_list_not_subset_of_task_architectures_is_skipped(self):
        task = _task(["historian"])

        arms = resolve_architecture_arms("historian,opcua", task)

        assert arms == []

    def test_unknown_raw_architecture_is_skipped_not_run(self):
        task = _task(["historian"])

        arms = resolve_architecture_arms("i3x", task)

        assert arms == []


class TestGetGitCommit:
    def test_returns_a_commit_hash_or_none(self):
        # Best-effort: in this repo (a real git checkout) it should
        # resolve to a real commit hash; the important contract is that
        # it never raises.
        commit = get_git_commit()
        assert commit is None or (isinstance(commit, str) and len(commit) == 40)


class TestBenchmarkConfig:
    def test_defaults(self):
        config = BenchmarkConfig(suite="tep-v1")
        assert config.agent == "llm"
        assert config.architectures == "all"
        assert config.repetitions == 1
        assert config.seeds is None

    def test_rejects_unknown_fields(self):
        with pytest.raises(Exception):
            BenchmarkConfig(suite="tep-v1", bogus_field=True)

    def test_benchmark_suite_version_is_a_string(self):
        assert isinstance(BENCHMARK_SUITE_VERSION, str)
        assert BENCHMARK_SUITE_VERSION
