"""
M13-C: BenchmarkTask ground-truth isolation -- extends
tests/unit/scenarios/test_hidden_ground_truth.py's structural guarantee
(the agent never sees `ground_truth`) to the TASK level, since a task's
own `objective` is now what actually reaches the agent, distinct from
its underlying scenario's objective.
"""

import pytest

from icab.agent.llm.agent import LLMInvestigationAgent
from icab.agent.llm.client import LLMResponse, MockLLMClient
from icab.scenarios.models import GroundTruth, ScenarioDifficulty, TaskMode
from icab.tasks.benchmark_task import BenchmarkTask, EvaluationCriteria
from icab.tasks.context_dimensions import ContextDimension


def _task(objective: str, *, disturbance: str = "idv_06") -> BenchmarkTask:
    return BenchmarkTask(
        task_id="hidden-gt-task-test",
        scenario_id="d4_plant_wide_investigation",
        task_type=TaskMode.DIAGNOSIS,
        difficulty=ScenarioDifficulty.D4,
        objective=objective,
        available_architectures=["historian"],
        required_context_dimensions=[ContextDimension.C5_OPERATIONAL],
        ground_truth=GroundTruth(
            conclusion=f"The root cause is {disturbance}.",
            root_cause_disturbance=disturbance,
            affected_measurements=["urn:icab:measurement:stripper_level"],
            affected_equipment=["urn:icab:equipment:stripper"],
        ),
        evaluation_criteria=EvaluationCriteria(binding_scores=["required_evidence_score"]),
    )


def test_benchmark_task_model_has_no_objective_leak_guard_of_its_own():
    """
    Unlike BenchmarkScenario (which has an enforced validator, since a
    scenario's objective is ALSO agent-visible for scenarios with no
    task layer on top), BenchmarkTask intentionally does not duplicate
    that validator -- a task's objective is a free-form field authored
    independently of any one scenario's fault, and this suite's own task
    authoring keeps objectives fault-id-free by convention, checked by
    test_task_objectives_never_mention_their_own_fault below against the
    REAL checked-in tasks. This test just documents that omission is
    deliberate, not an oversight.
    """

    # Constructing a task whose objective mentions its own fault id does
    # NOT raise -- confirming the above is accurate, not aspirational.
    task = _task("Investigate the idv_06 disturbance.")
    assert "idv_06" in task.objective.lower()


def test_task_ground_truth_is_never_in_the_agents_initial_state():
    task = _task("Investigate why the plant is behaving abnormally.")

    initial_state = {"scenario_id": task.scenario_id, "difficulty": task.difficulty.value}
    serialized = f"{task.objective} {initial_state}".lower()

    assert "idv_06" not in serialized
    assert "stripper_level" not in serialized


def test_llm_agent_messages_never_contain_the_tasks_ground_truth():
    task = _task("Investigate why the plant is behaving abnormally.")

    llm = MockLLMClient([LLMResponse(content="I don't know yet.", tool_calls=())])

    class _StubGatewayClient:
        trace_collector = None

    agent = LLMInvestigationAgent(_StubGatewayClient(), llm, max_steps=1)
    agent.run(
        objective=task.objective,
        initial_state={"scenario_id": task.scenario_id, "difficulty": task.difficulty.value},
    )

    sent_messages = str(llm.calls[0]["messages"]).lower()
    assert "idv_06" not in sent_messages
    assert "stripper_level" not in sent_messages
    assert task.ground_truth.conclusion.lower() not in sent_messages


@pytest.mark.parametrize(
    "tasks_yaml",
    [
        "configs/benchmark/tasks/d1_reactor_pressure_reading.yaml",
        "configs/benchmark/tasks/d2_reactor_context_combination.yaml",
        "configs/benchmark/tasks/d2_reactor_cooling_deviation.yaml",
        "configs/benchmark/tasks/d3_reactor_pressure_deviation.yaml",
        "configs/benchmark/tasks/d3_stream4_composition_shift.yaml",
        "configs/benchmark/tasks/d3_stochastic_composition_drift.yaml",
        "configs/benchmark/tasks/d4_plant_wide_investigation.yaml",
        "configs/benchmark/tasks/d4_unknown_plant_disturbance.yaml",
        "configs/benchmark/tasks/d4_feed_pressure_reactor_effect.yaml",
    ],
)
def test_task_objectives_never_mention_their_own_fault(tasks_yaml):
    """Every REAL, checked-in task's objective must never mention its own
    ground_truth.root_cause_disturbance -- checked directly against the
    committed YAML, not just the model layer (which, per the test above,
    would not itself reject it)."""

    from icab.tasks.registry import load_benchmark_tasks

    for task in load_benchmark_tasks(tasks_yaml):
        disturbance = task.ground_truth.root_cause_disturbance
        if disturbance is None:
            continue
        assert disturbance.lower() not in task.objective.lower(), task.task_id
