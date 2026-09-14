"""
M13-D: one-command ICAB benchmark orchestration CLI.

Requires the Agent Gateway running separately (same convention as
`scripts/run_experiment.py` and the other `scripts/run_*_agent.py`
scripts)::

    uv run uvicorn icab.gateway.app:app --reload

Full benchmark, every LLM-eligible architecture, five seeds::

    uv run python scripts/run_benchmark.py \\
        --suite tep-v1 \\
        --agent llm \\
        --architectures all \\
        --seeds 1,2,3,4,5

Fast smoke test -- one task, one architecture, one seed, the
deterministic baseline (exercises the real orchestration path end to
end, just over a tiny subset)::

    uv run python scripts/run_benchmark.py \\
        --suite tep-v1 \\
        --split development \\
        --task d1-qa-current-pressure \\
        --agent baseline \\
        --architectures historian \\
        --seeds 1

Every run is persisted under results/{raw,traces,evaluations}/, and the
whole invocation's aggregate/report is written under
results/{aggregate,reports,figures}/ automatically -- see
docs/benchmark/specification.md for the full output layout and
reproducibility guarantees.
"""

from __future__ import annotations

import argparse
import sys

from icab.benchmark import BenchmarkConfig, BenchmarkRunner
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.experiments import ExperimentResultStore, ExperimentRunner
from icab.experiments.architecture_combinations import list_combination_keys
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync

DEFAULT_GATEWAY_URL = "http://localhost:8000"


def _build_benchmark_runner(gateway_url: str, results_root: str) -> tuple[BenchmarkRunner, MQTTClient, Neo4jKnowledgeGraphRepository]:
    """
    Wires the same real infrastructure `scripts/run_experiment.py` uses
    (historian/knowledge-graph/MQTT/context-sync), then builds an
    `ExperimentRunner` over it and a `BenchmarkRunner` on top -- the
    orchestration layer adds no infrastructure of its own.

    A benchmark invocation may run against tasks from several DIFFERENT
    scenarios (unlike `run_experiment.py`'s single fixed
    `BenchmarkScenarioRegistry`), so `BenchmarkRunner.run()` builds its
    own scenario/task registries per-suite internally -- the
    `ExperimentRunner` passed in here still needs *a* registry at
    construction time (for its base API), which `BenchmarkRunner`
    overrides per run_task() call via its own `scenario=` argument.
    """

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
    publisher = TEPMeasurementPublisher(mqtt_client, source="run_benchmark")

    context_sync = TEPContextSync(
        environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph),
        mqtt_publisher=publisher,
    )

    # A placeholder registry: BenchmarkRunner.run() always resolves the
    # ACTUAL suite scenario directory itself (see icab.benchmark.runner)
    # and passes each run's real scenario in explicitly via run_task's
    # `scenario=` argument, so this constructor-time registry is never
    # consulted for a benchmark invocation's own scenario lookups.
    experiment_runner = ExperimentRunner(
        gateway_base_url=gateway_url,
        scenario_runner=ScenarioRunner(context_sync=context_sync),
        scenario_registry=BenchmarkScenarioRegistry("configs/benchmark/scenarios"),
    )

    benchmark_runner = BenchmarkRunner(
        experiment_runner=experiment_runner,
        experiment_store=ExperimentResultStore(root=results_root),
    )

    return benchmark_runner, mqtt_client, knowledge_graph_repository


def _parse_seeds(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--suite", required=True, help="Registered benchmark suite, e.g. 'tep-v1'.")
    parser.add_argument("--split", choices=["development", "validation", "test"], default=None,
                         help="Restrict to tasks whose scenario is in this split. Default: every split.")
    parser.add_argument("--task", dest="task_id", default=None, help="Restrict to one explicit task_id (overrides --split/--scenario).")
    parser.add_argument("--scenario", dest="scenario_id", default=None, help="Restrict to tasks against this one scenario_id.")

    parser.add_argument(
        "--agent",
        default="llm",
        help=(
            "'baseline' (ScenarioAwareBaselineAgent) or 'llm' (LLMInvestigationAgent) -- "
            "the two benchmark-eligible agents. A legacy DeterministicAgentKind value "
            "(e.g. 'structured_retrieval') is also accepted as an explicit, separate "
            "opt-in for a labeled legacy control -- never the default, and always "
            "excluded from normal aggregates (RunValidity.LEGACY_CONTROL_ONLY)."
        ),
    )
    parser.add_argument(
        "--architectures",
        default="all",
        help=(
            "'all' (one arm per architecture the task itself declares available), "
            f"a named combination key ({', '.join(list_combination_keys())}), or a raw "
            "comma-separated architecture list -- always validated against each task's "
            "own available_architectures; an unsupported combination is SKIPPED, not run."
        ),
    )
    parser.add_argument("--seeds", default=None, help="Comma-separated seed overrides, e.g. '1,2,3,4,5'. Default: each scenario's own built-in seed, once.")
    parser.add_argument("--repetitions", type=int, default=1, help="Repeat each (task, architecture arm, seed) this many times.")

    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--temperature", dest="llm_temperature", type=float, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    parser.add_argument("--max-context-tokens", type=int, default=None)
    parser.add_argument("--max-wall-time", dest="max_wall_time_seconds", type=float, default=None)

    parser.add_argument("--name", default=None, help="Benchmark/experiment id -- default: auto-generated.")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--results-root", default="results")

    return parser


def build_benchmark_config(args: argparse.Namespace) -> BenchmarkConfig:
    return BenchmarkConfig(
        suite=args.suite,
        split=args.split,
        task_id=args.task_id,
        scenario_id=args.scenario_id,
        agent=args.agent,
        architectures=args.architectures,
        seeds=_parse_seeds(args.seeds),
        repetitions=args.repetitions,
        llm_model=args.llm_model,
        llm_temperature=args.llm_temperature,
        max_steps=args.max_steps,
        max_tool_calls=args.max_tool_calls,
        max_context_tokens=args.max_context_tokens,
        max_wall_time_seconds=args.max_wall_time_seconds,
        name=args.name,
    )


def main() -> int:
    args = build_parser().parse_args()
    config = build_benchmark_config(args)

    benchmark_runner, mqtt_client, kg_repository = _build_benchmark_runner(args.gateway_url, args.results_root)

    try:
        with mqtt_client:
            result = benchmark_runner.run(config)
    finally:
        kg_repository.close()

    print(f"benchmark_id:      {result.benchmark_id}")
    print(f"suite:             {result.suite}   split: {result.split or '(all)'}")
    print(f"tasks:             {len(result.task_ids)}   scenarios: {len(result.scenario_ids)}")
    print(f"architectures:     {', '.join(result.architectures) or '(none)'}")
    print(f"agent:             {result.agent}")
    print(f"seeds:             {result.seeds or '(scenario default)'}   repetitions: {result.repetitions}")
    print(
        f"runs:              total={result.total_runs} "
        f"successful={result.successful_runs} failed={result.failed_runs} skipped={result.skipped_runs}"
    )
    for reason in result.skipped_reasons:
        print(f"  skipped:         {reason}")
    print(f"aggregate:         {result.aggregate_json_path}")
    print(f"                   {result.aggregate_csv_path}")
    print(f"report:            {result.report_json_path}")
    print(f"                   {result.report_markdown_path}")
    for figure_path in result.figure_paths:
        print(f"figure:            {figure_path}")

    return 1 if result.failed_runs > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
