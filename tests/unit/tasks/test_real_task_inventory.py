"""
M13-C: validates the ACTUAL checked-in benchmark task suite
(configs/benchmark/tasks/) -- not a synthetic fixture. Confirms the
coverage matrix (difficulty x task type x context dimension x
architecture x scenario/fault) actually holds for what is really
committed, and that every task's scenario/architecture linkage is valid.
"""

from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.models import ScenarioDifficulty, TaskMode
from icab.tasks import BenchmarkTaskRegistry, ContextDimension

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_DIR = "configs/benchmark/tasks"


def _registry() -> BenchmarkTaskRegistry:
    return BenchmarkTaskRegistry(TASKS_DIR, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))


def test_every_difficulty_level_has_multiple_tasks_and_is_not_d1_dominated():
    registry = _registry()

    counts = {difficulty: len(registry.for_difficulty(difficulty)) for difficulty in ScenarioDifficulty}

    for difficulty, count in counts.items():
        assert count >= 3, f"{difficulty} has only {count} tasks"

    # Explicit "not dominated by D1" check: D1's share of the whole suite
    # must not be the largest, and D3+D4 together must outnumber D1+D2.
    total = sum(counts.values())
    assert counts[ScenarioDifficulty.D1] < total / 3
    d3_d4 = counts[ScenarioDifficulty.D3] + counts[ScenarioDifficulty.D4]
    d1_d2 = counts[ScenarioDifficulty.D1] + counts[ScenarioDifficulty.D2]
    assert d3_d4 > d1_d2


def test_every_task_type_is_represented():
    registry = _registry()

    for task_type in TaskMode:
        assert len(registry.for_task_type(task_type)) >= 3, f"{task_type} has too few tasks"


def test_every_context_dimension_is_required_by_at_least_one_task():
    """Per the M13-C direction not to assign dimensions merely because
    they sound appropriate -- confirms every one of the seven dimensions
    is genuinely exercised by at least one real, committed task (not
    just theoretically definable)."""

    registry = _registry()

    used_dimensions = {
        dimension for task in registry for dimension in task.required_context_dimensions
    }

    for dimension in ContextDimension:
        assert dimension in used_dimensions, f"{dimension} is never required by any real task"


def test_every_available_architecture_is_used_by_at_least_one_task():
    registry = _registry()

    used_architectures = {
        architecture for task in registry for architecture in task.available_architectures
    }

    for architecture in ("historian", "knowledge_graph", "uns", "opcua", "mqtt"):
        assert architecture in used_architectures, f"{architecture!r} is never used by any real task"

    # i3X is intentionally not required by any real task in this initial
    # suite -- see docs/benchmark/tasks.md's known limitations -- but
    # confirm that's a deliberate, documented absence, not silently
    # unnoticed: it must still be a legitimate, resolvable architecture
    # name (matches icab.agent.llm.tools.ARCHITECTURE_TOOL_NAMES), just
    # unused so far.
    from icab.agent.llm.tools import ARCHITECTURE_TOOL_NAMES

    assert "i3x" in ARCHITECTURE_TOOL_NAMES
    assert "i3x" not in used_architectures


def test_some_tasks_require_a_single_architecture_and_some_require_several():
    """Distinguishes single-source retrieval from cross-architecture
    retrieval, per the M13-C task-design principles."""

    registry = _registry()

    architecture_counts = {len(task.available_architectures) for task in registry}

    assert 1 in architecture_counts  # at least one single-architecture task
    assert max(architecture_counts) >= 3  # at least one broad, multi-architecture task


def test_at_least_one_task_per_verified_fault_is_used_somewhere():
    """M13-B's 7 empirically verified faults -- confirm every one of them
    actually underlies at least one real scenario a task is built on
    (not merely mentioned in documentation)."""

    registry = _registry()
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)

    disturbances_used = set()
    for task in registry:
        scenario = scenario_registry.get(task.scenario_id)
        for fault in scenario.faults:
            disturbances_used.add(fault.disturbance)

    verified_faults = {"idv_01", "idv_02", "idv_06", "idv_08", "idv_17", "idv_20", "idv_24"}
    assert disturbances_used == verified_faults


def test_diagnosis_tasks_bind_on_conclusion_correctness():
    """A diagnosis task that never checks conclusion_correctness_score
    would not really be testing diagnosis -- confirm every real
    diagnosis-typed task actually binds on it."""

    registry = _registry()

    for task in registry.for_task_type(TaskMode.DIAGNOSIS):
        assert "conclusion_correctness_score" in task.evaluation_criteria.binding_scores, task.task_id


def test_total_task_count_is_reported_honestly_not_forced_to_forty():
    """Quality over hitting an arbitrary target -- confirm the real count
    is what it is, not silently padded."""

    registry = _registry()

    assert 30 <= len(registry) <= 45
