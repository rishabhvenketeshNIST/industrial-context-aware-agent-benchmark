"""
Command-line entry point for M9 experiments.

Requires the Agent Gateway running separately (same convention as the
other `scripts/run_*_agent.py` scripts):

    uv run uvicorn icab.gateway.app:app --reload

Single run::

    uv run python scripts/run_experiment.py \\
        --scenario d1_reactor_pressure_reading \\
        --architectures historian \\
        --agent-type llm

Deterministic baseline::

    uv run python scripts/run_experiment.py \\
        --scenario d1_reactor_pressure_reading \\
        --architectures historian \\
        --agent-type deterministic --deterministic-agent structured_retrieval

Architecture comparison (same scenario/seed/fault, only tools vary) --
pass --architectures more than once, each a comma-separated group::

    uv run python scripts/run_experiment.py --compare \\
        --scenario d3_reactor_pressure_deviation \\
        --architectures historian \\
        --architectures historian,knowledge_graph \\
        --agent-type llm

Every run is persisted under results/{raw,traces,evaluations}/; --compare
additionally writes results/aggregate/<experiment_id>.{json,csv}.
"""

from __future__ import annotations

import argparse
import sys

from icab.agent.llm.tools import ARCHITECTURE_TOOL_NAMES
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.experiments import AgentType, DeterministicAgentKind, ExperimentConfig, ExperimentResultStore, ExperimentRunner
from icab.experiments.models import ExperimentRunStatus
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync

SCENARIOS_DIR = "configs/benchmark/scenarios"
DEFAULT_GATEWAY_URL = "http://localhost:8000"


def _build_runner(gateway_url: str) -> tuple[ExperimentRunner, MQTTClient, Neo4jKnowledgeGraphRepository]:
    from icab.common.config import get_settings

    settings = get_settings()

    historian = HistorianService(PostgresHistorianRepository(settings.database_url))
    knowledge_graph_repository = Neo4jKnowledgeGraphRepository(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
    )
    knowledge_graph = KnowledgeGraphService(knowledge_graph_repository)

    mqtt_client = MQTTClient(settings.mqtt_host, settings.mqtt_port)
    publisher = TEPMeasurementPublisher(mqtt_client, source="run_experiment")

    context_sync = TEPContextSync(
        environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph),
        mqtt_publisher=publisher,
    )

    runner = ExperimentRunner(
        gateway_base_url=gateway_url,
        scenario_runner=ScenarioRunner(context_sync=context_sync),
        scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR),
    )

    # Caller must `with mqtt_client:` around the run -- TEPContextSync.sync()
    # calls mqtt_publisher.publish_state(), which requires an open connection
    # for the whole scenario preparation (potentially many sync calls).
    return runner, mqtt_client, knowledge_graph_repository


def _print_record(record) -> None:
    print(f"run_id:            {record.run_id}")
    print(f"experiment_id:     {record.experiment_id}")
    print(f"scenario:          {record.config.scenario_id} ({record.scenario_difficulty})")
    print(f"architectures:     {'+'.join(record.config.architectures)}")
    print(f"agent:             {record.config.agent_type.value}"
          + (f" / {record.config.deterministic_agent.value}" if record.config.deterministic_agent else ""))
    if record.config.agent_type == AgentType.LLM:
        print(f"model:             {record.config.llm_model} (temperature={record.config.llm_temperature})")
    print(f"simulation_seed:   {record.simulation_seed}")
    print(f"status:            {record.status.value}")
    if record.error:
        print(f"error:             {record.error}")
    if record.result is not None:
        print(f"termination:       {record.result.termination.value}")
        print(f"conclusion:        {record.result.conclusion}")
    if record.evaluation is not None:
        ev = record.evaluation
        print(
            "scores:            "
            f"required_evidence={ev.required_evidence_score:.2f} "
            f"relationship={ev.relationship_score:.2f} "
            f"conclusion_correctness={ev.conclusion_correctness_score:.2f} "
            f"grounding={ev.grounding_score:.2f} "
            f"completeness={ev.completeness_score:.2f}"
        )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, help="Scenario id from configs/benchmark/scenarios/")
    parser.add_argument(
        "--architectures",
        action="append",
        required=True,
        help=(
            f"Comma-separated architecture names ({', '.join(ARCHITECTURE_TOOL_NAMES)}). "
            "Pass more than once with --compare to run each group against the same scenario."
        ),
    )
    parser.add_argument("--agent-type", choices=[t.value for t in AgentType], default=AgentType.LLM.value)
    parser.add_argument("--deterministic-agent", choices=[k.value for k in DeterministicAgentKind], default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-temperature", type=float, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--compare", action="store_true", help="Run every --architectures group against one shared scenario preparation.")
    parser.add_argument("--results-root", default="results")

    args = parser.parse_args()

    architecture_groups = [group.split(",") for group in args.architectures]
    runner, mqtt_client, kg_repository = _build_runner(args.gateway_url)
    store = ExperimentResultStore(root=args.results_root)

    try:
        with mqtt_client:
            if args.compare or len(architecture_groups) > 1:
                runs = runner.compare_architectures(
                    args.scenario,
                    architecture_groups,
                    agent_type=AgentType(args.agent_type),
                    deterministic_agent=(
                        DeterministicAgentKind(args.deterministic_agent)
                        if args.deterministic_agent
                        else None
                    ),
                    llm_model=args.llm_model,
                    llm_temperature=args.llm_temperature,
                    max_steps=args.max_steps,
                    experiment_id=args.experiment_id,
                )

                records = []
                for record, trace in runs:
                    store.save(record, trace)
                    _print_record(record)
                    records.append(record)

                experiment_id = records[0].experiment_id
                json_path, csv_path = store.write_aggregate(experiment_id, records)
                print(f"Aggregate written to: {json_path}")
                print(f"                      {csv_path}")

                return 1 if any(r.status == ExperimentRunStatus.FAILED for r in records) else 0

            config = ExperimentConfig(
                scenario_id=args.scenario,
                architectures=architecture_groups[0],
                agent_type=AgentType(args.agent_type),
                deterministic_agent=(
                    DeterministicAgentKind(args.deterministic_agent)
                    if args.deterministic_agent
                    else None
                ),
                llm_model=args.llm_model,
                llm_temperature=args.llm_temperature,
                max_steps=args.max_steps,
            )

            record, trace = runner.run(config, experiment_id=args.experiment_id)
            store.save(record, trace)
            _print_record(record)
            print(
                f"Saved: results/raw/{record.run_id}.json, results/traces/{record.run_id}.jsonl"
                + (f", results/evaluations/{record.run_id}.json" if record.evaluation else "")
            )

            return 1 if record.status == ExperimentRunStatus.FAILED else 0
    finally:
        kg_repository.close()


if __name__ == "__main__":
    sys.exit(main())
