from unittest.mock import Mock

import httpx
import pytest

from icab.agent.interface import TerminationReason
from icab.agent.llm.client import LLMResponse, MockLLMClient, ToolCall
from icab.experiments import (
    AgentType,
    DeterministicAgentKind,
    ExperimentConfig,
    ExperimentRunStatus,
    ExperimentRunner,
)
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner

SCENARIOS_DIR = "configs/benchmark/scenarios"


def _registry() -> BenchmarkScenarioRegistry:
    return BenchmarkScenarioRegistry(SCENARIOS_DIR)


def _mock_scenario_runner() -> Mock:
    return Mock(spec=ScenarioRunner)


def _patch_gateway(monkeypatch, response_json: dict) -> None:
    def fake_post(url, **kwargs):
        return httpx.Response(200, json=response_json, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)


def test_run_llm_experiment_completes_and_evaluates(monkeypatch):
    _patch_gateway(
        monkeypatch,
        {
            "observation": {
                "measurement_id": "urn:icab:measurement:reactor_pressure",
                "value": 2705.0,
                "unit": "kPa gauge",
            }
        },
    )

    llm = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="get_current_value",
                        arguments={"measurement_id": "urn:icab:measurement:reactor_pressure"},
                    ),
                ),
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(id="call-2", name="submit_investigation", arguments={"conclusion": "2705 kPa, normal."}),
                ),
            ),
        ]
    )

    runner = ExperimentRunner(
        gateway_base_url="http://localhost:8000",
        scenario_runner=_mock_scenario_runner(),
        scenario_registry=_registry(),
        llm_client_factory=lambda config: llm,
    )

    config = ExperimentConfig(
        scenario_id="d1_reactor_pressure_reading",
        architectures=["historian"],
        agent_type=AgentType.LLM,
    )

    record, trace = runner.run(config, run_id="test-run-1")

    assert record.status == ExperimentRunStatus.COMPLETED
    assert record.error is None
    assert record.result is not None
    assert record.result.termination == TerminationReason.SUBMITTED
    assert record.evaluation is not None
    assert record.evaluation.required_evidence_score == 1.0
    assert record.scenario_difficulty == "D1"
    assert record.simulation_seed == 101
    assert len(trace) == 1
    assert record.trace_event_count == 1

    # Defaults were resolved and captured for reproducibility.
    assert record.config.max_steps is not None
    assert record.config.llm_temperature == 0.0

    runner.scenario_runner.prepare.assert_called_once()


def test_run_deterministic_agent_clears_llm_fields(monkeypatch):
    _patch_gateway(
        monkeypatch,
        {"observation": {"value": 2705.0, "unit": "kPa gauge"}, "relationships": []},
    )

    runner = ExperimentRunner(
        gateway_base_url="http://localhost:8000",
        scenario_runner=_mock_scenario_runner(),
        scenario_registry=_registry(),
    )

    config = ExperimentConfig(
        scenario_id="d1_reactor_pressure_reading",
        architectures=["historian", "knowledge_graph"],
        agent_type=AgentType.DETERMINISTIC,
        deterministic_agent=DeterministicAgentKind.STRUCTURED_RETRIEVAL,
        llm_model="should-be-cleared",
    )

    record, _trace = runner.run(config)

    assert record.status == ExperimentRunStatus.COMPLETED
    assert record.config.llm_model is None
    assert record.config.llm_temperature is None
    assert record.config.max_steps is None


def test_architecture_aware_requires_exactly_one_architecture():
    runner = ExperimentRunner(
        gateway_base_url="http://localhost:8000",
        scenario_runner=_mock_scenario_runner(),
        scenario_registry=_registry(),
    )

    config = ExperimentConfig(
        scenario_id="d1_reactor_pressure_reading",
        architectures=["uns", "opcua"],
        agent_type=AgentType.DETERMINISTIC,
        deterministic_agent=DeterministicAgentKind.ARCHITECTURE_AWARE,
    )

    record, trace = runner.run(config)

    assert record.status == ExperimentRunStatus.FAILED
    assert "exactly one architecture" in record.error
    assert record.result is None
    assert record.evaluation is None
    assert trace == []


def test_missing_deterministic_agent_kind_fails_cleanly():
    runner = ExperimentRunner(
        gateway_base_url="http://localhost:8000",
        scenario_runner=_mock_scenario_runner(),
        scenario_registry=_registry(),
    )

    config = ExperimentConfig(
        scenario_id="d1_reactor_pressure_reading",
        architectures=["historian"],
        agent_type=AgentType.DETERMINISTIC,
    )

    record, _trace = runner.run(config)

    assert record.status == ExperimentRunStatus.FAILED
    assert record.error is not None


def test_compare_architectures_prepares_the_scenario_only_once(monkeypatch):
    _patch_gateway(monkeypatch, {})

    def llm_factory(config):
        return MockLLMClient([LLMResponse(content="done", tool_calls=())])

    scenario_runner = _mock_scenario_runner()
    runner = ExperimentRunner(
        gateway_base_url="http://localhost:8000",
        scenario_runner=scenario_runner,
        scenario_registry=_registry(),
        llm_client_factory=llm_factory,
    )

    runs = runner.compare_architectures(
        "d1_reactor_pressure_reading",
        [["historian"], ["knowledge_graph"]],
    )

    assert len(runs) == 2
    scenario_runner.prepare.assert_called_once()

    experiment_ids = {record.experiment_id for record, _ in runs}
    assert len(experiment_ids) == 1  # same experiment_id groups both runs

    run_ids = {record.run_id for record, _ in runs}
    assert len(run_ids) == 2  # but each run has its own run_id


def test_run_id_defaults_are_stable_and_include_scenario_and_architectures():
    runner = ExperimentRunner(
        gateway_base_url="http://localhost:8000",
        scenario_runner=_mock_scenario_runner(),
        scenario_registry=_registry(),
    )

    config = ExperimentConfig(
        scenario_id="d1_reactor_pressure_reading",
        architectures=["historian"],
        agent_type=AgentType.DETERMINISTIC,
        deterministic_agent=DeterministicAgentKind.STRUCTURED_RETRIEVAL,
    )

    run_id = runner._default_run_id(config)

    assert run_id.startswith("d1_reactor_pressure_reading-historian-")
