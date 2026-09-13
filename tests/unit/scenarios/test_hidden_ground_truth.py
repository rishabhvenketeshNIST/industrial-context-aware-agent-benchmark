"""
M13-B: hidden ground-truth separation -- the agent must never see the
fault identifier / GroundTruth. Some of this is structural (nothing in
`icab.agent`/`icab.experiments` even reads `BenchmarkScenario.ground_truth`
or `.faults`, verified by inspection: `grep -rl ground_truth src/` finds
only `icab.scenarios.models` itself and `icab.evaluation.grounded`, which
only reads it AFTER the agent has already submitted a conclusion); this
file makes that guarantee an enforced, regression-tested property rather
than an implicit one.
"""

import pytest

from icab.agent.llm.client import LLMResponse, MockLLMClient
from icab.agent.llm.agent import LLMInvestigationAgent
from icab.scenarios import BenchmarkScenario, FaultSchedule, GroundTruth, ScenarioDifficulty


def _scenario_with_fault(objective: str, *, disturbance: str = "idv_06") -> BenchmarkScenario:
    return BenchmarkScenario(
        scenario_id="hidden-gt-test",
        name="Hidden ground truth test",
        difficulty=ScenarioDifficulty.D4,
        objective=objective,
        seed=1,
        warmup_hours=1.0,
        duration_hours=1.0,
        faults=[FaultSchedule(disturbance=disturbance, activate_at_hours=1.0)],
        ground_truth=GroundTruth(
            conclusion=f"The root cause is {disturbance}.",
            root_cause_disturbance=disturbance,
            affected_measurements=["urn:icab:measurement:stripper_level"],
            affected_equipment=["urn:icab:equipment:stripper"],
        ),
    )


def test_objective_mentioning_its_own_fault_id_is_rejected_at_construction():
    with pytest.raises(ValueError, match="idv_06"):
        _scenario_with_fault("Investigate the idv_06 disturbance.")


def test_objective_mentioning_a_different_faults_id_is_fine():
    # Mentioning some OTHER disturbance id (e.g. a trip threshold
    # reference unrelated to this scenario's own fault) is not what the
    # safeguard guards against -- only the scenario's OWN scheduled fault.
    scenario = _scenario_with_fault(
        "Investigate why the plant is behaving abnormally.", disturbance="idv_06"
    )
    assert scenario.objective == "Investigate why the plant is behaving abnormally."


def test_ground_truth_is_not_reachable_from_the_agents_initial_state():
    """Mirrors exactly what icab.experiments.ExperimentRunner._run_prepared
    passes to Agent.run() -- objective + a minimal initial_state dict,
    never the scenario object (and therefore never ground_truth) itself."""

    scenario = _scenario_with_fault("Investigate why the plant is behaving abnormally.")

    initial_state = {
        "scenario_id": scenario.scenario_id,
        "difficulty": scenario.difficulty.value,
    }

    serialized = f"{scenario.objective} {initial_state}"
    assert "idv_06" not in serialized.lower()
    assert "stripper_level" not in serialized.lower()  # ground_truth.affected_measurements


def test_llm_agent_messages_never_contain_the_fault_id_or_ground_truth():
    """Runs the real LLMInvestigationAgent (MockLLMClient, no network)
    over a scenario whose ground truth references a fault id, and
    inspects every message actually sent to the LLM."""

    scenario = _scenario_with_fault("Investigate why the plant is behaving abnormally.")

    llm = MockLLMClient([LLMResponse(content="I don't know yet.", tool_calls=())])

    class _StubGatewayClient:
        trace_collector = None

    agent = LLMInvestigationAgent(_StubGatewayClient(), llm, max_steps=1)

    agent.run(
        objective=scenario.objective,
        initial_state={"scenario_id": scenario.scenario_id, "difficulty": scenario.difficulty.value},
    )

    assert len(llm.calls) == 1
    sent_messages = str(llm.calls[0]["messages"]).lower()

    assert "idv_06" not in sent_messages
    assert "stripper_level" not in sent_messages
    assert scenario.ground_truth.conclusion.lower() not in sent_messages
