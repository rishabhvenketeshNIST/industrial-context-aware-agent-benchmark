"""
Command-line entry point for M11 hypothesis-comparison experiments.

Runs the treatment/control architecture-combination pair a locked
hypothesis (H1-H5, `icab.experiments.hypotheses`) is defined against,
against one shared scenario preparation, then computes and persists a
descriptive (NOT inferential -- see `icab.experiments.hypotheses` module
docstring) comparison of that hypothesis's metric between the two arms.

Requires the Agent Gateway running separately, same as
`scripts/run_experiment.py`:

    uv run uvicorn icab.gateway.app:app --reload

Usage::

    uv run python scripts/run_hypothesis_experiment.py \\
        --scenario d4_plant_wide_investigation --hypothesis H3

    # repeat the same scenario/combination pair N times (the only kind of
    # "seed sweep" possible while one scenario per difficulty exists --
    # see docs/benchmark/tasks.md) to get more than one point per arm:
    uv run python scripts/run_hypothesis_experiment.py \\
        --scenario d4_plant_wide_investigation --hypothesis H3 --repeat 3

Every underlying run is persisted exactly like scripts/run_experiment.py
(results/{raw,traces,evaluations,aggregate}/); the hypothesis comparison
itself is additionally written to results/hypotheses/<experiment_id>-<H?>.json.
"""

from __future__ import annotations

import argparse
import sys

from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.experiments import ExperimentResultStore, ExperimentRunner
from icab.experiments.hypotheses import HypothesisID, combinations_for_hypothesis, evaluate_hypothesis, get_spec
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
    publisher = TEPMeasurementPublisher(mqtt_client, source="run_hypothesis_experiment")

    context_sync = TEPContextSync(
        environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph),
        mqtt_publisher=publisher,
    )

    runner = ExperimentRunner(
        gateway_base_url=gateway_url,
        scenario_runner=ScenarioRunner(context_sync=context_sync),
        scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR),
    )

    return runner, mqtt_client, knowledge_graph_repository


def _print_result(result) -> None:
    print(f"hypothesis:        {result.hypothesis.value} -- {result.statement}")
    print(f"metric:            {result.metric} (higher_is_better={result.higher_is_better})")
    print(f"treatment:         {'+'.join(result.treatment_combinations)}  n={len(result.treatment_values)}  values={result.treatment_values}")
    print(f"control:           {'+'.join(result.control_combinations)}  n={len(result.control_values)}  values={result.control_values}")
    print(f"treatment_mean:    {result.treatment_mean}")
    print(f"control_mean:      {result.control_mean}")
    print(f"mean_difference:   {result.mean_difference}")
    print(f"direction supports hypothesis: {result.direction_supports_hypothesis}")
    print(f"NOTE: {result.caveat}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, help="Scenario id from configs/benchmark/scenarios/")
    parser.add_argument("--hypothesis", required=True, choices=[h.value for h in HypothesisID])
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-temperature", type=float, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--experiment-id", default=None)
    parser.add_argument("--results-root", default="results")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help=(
            "Run the scenario/combination pair this many times (each a fresh scenario "
            "preparation). Only one real scenario per difficulty currently exists, so "
            "this varies LLM stochasticity/wall-clock conditions, not the seed -- not a "
            "substitute for a genuine multi-seed sweep. See docs/benchmark/tasks.md."
        ),
    )

    args = parser.parse_args()

    spec = get_spec(args.hypothesis)
    combination_keys = combinations_for_hypothesis(spec)

    runner, mqtt_client, kg_repository = _build_runner(args.gateway_url)
    store = ExperimentResultStore(root=args.results_root)

    experiment_id = args.experiment_id or f"hyp-{spec.id.value}-{args.scenario}"

    all_records = []
    any_failed = False

    try:
        with mqtt_client:
            for repeat_index in range(args.repeat):
                run_experiment_id = experiment_id if args.repeat == 1 else f"{experiment_id}-{repeat_index}"

                runs = runner.compare_combinations(
                    args.scenario,
                    combination_keys,
                    llm_model=args.llm_model,
                    llm_temperature=args.llm_temperature,
                    max_steps=args.max_steps,
                    experiment_id=run_experiment_id,
                )

                for record, trace in runs:
                    store.save(record, trace)
                    print(
                        f"[{run_experiment_id}] {record.config.architecture_combination_key}: "
                        f"status={record.status.value} validity={record.validity.value}"
                    )
                    all_records.append(record)
                    if record.status == ExperimentRunStatus.FAILED:
                        any_failed = True
        print()

        result = evaluate_hypothesis(spec, all_records)
        _print_result(result)

        path = store.write_hypothesis_result(result, experiment_id=experiment_id)
        print(f"Hypothesis result written to: {path}")

        return 1 if any_failed else 0
    finally:
        kg_repository.close()


if __name__ == "__main__":
    sys.exit(main())
