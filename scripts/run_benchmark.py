"""
M13-D: one-command ICAB benchmark orchestration CLI.

Requires the Agent Gateway running separately (same convention as
`scripts/run_experiment.py` and the other `scripts/run_*_agent.py`
scripts)::

    uv run uvicorn icab.gateway.app:app --reload

If it isn't reachable, this script fails immediately with an actionable
message (`_check_gateway_reachable`) rather than letting every run
independently fail with a bare connection error after an already-
completed, expensive scenario preparation.

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

import psycopg
from neo4j import GraphDatabase

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


def _check_infrastructure_reachable(settings) -> None:
    """
    Fail fast, with one clear, consolidated message, if PostgreSQL/
    TimescaleDB, Neo4j, or MQTT aren't reachable. Constructing
    `PostgresHistorianRepository`/`Neo4jKnowledgeGraphRepository`/
    `MQTTClient` never actually connects (all three connect lazily, on
    first real use) -- without this check, an unreachable service would
    only surface deep inside the FIRST scenario preparation, as a raw
    driver exception, and then identically again for every subsequent
    run in the invocation. Mirrors `_check_gateway_reachable`'s
    rationale; the Agent Gateway's own `/health` is a static check and
    does not itself verify these services.
    """

    problems: list[str] = []

    try:
        with psycopg.connect(settings.database_url, connect_timeout=5):
            pass
    except Exception as error:  # noqa: BLE001 -- reported, not silenced
        problems.append(f"PostgreSQL/TimescaleDB ({settings.database_url}): {type(error).__name__}: {error}")

    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password)
        )
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
    except Exception as error:  # noqa: BLE001
        problems.append(f"Neo4j ({settings.neo4j_uri}): {type(error).__name__}: {error}")

    try:
        probe = MQTTClient(settings.mqtt_host, settings.mqtt_port)
        probe.connect()
        probe.disconnect()
    except Exception as error:  # noqa: BLE001
        problems.append(f"MQTT ({settings.mqtt_host}:{settings.mqtt_port}): {type(error).__name__}: {error}")

    if problems:
        details = "\n  - ".join(problems)
        raise SystemExit(
            "error: required infrastructure is not reachable:\n  - " + details + "\n\n"
            "Start the docker-compose stack first:\n"
            "    docker compose up -d\n"
            "then re-run this command."
        )


def _check_gateway_reachable(gateway_url: str) -> None:
    """
    Fail fast, with an actionable message, if the Agent Gateway isn't
    reachable at `gateway_url` -- otherwise every single (task,
    architecture, seed, repetition) run independently discovers this
    only AFTER a full, potentially expensive scenario preparation (a
    real TEP simulator run plus historian/knowledge-graph/MQTT sync),
    each ending up as its own persisted FAILED record carrying nothing
    more diagnosable than a raw `ConnectError`. One cheap, upfront
    `GET /health` check turns a systemic precondition failure into one
    clear message instead of N confusing, identical per-run ones.

    Deliberately does NOT touch `BenchmarkRunner`/`ExperimentRunner`
    themselves -- a per-run gateway call that fails for a genuine,
    run-specific reason (e.g. the gateway crashes partway through a long
    invocation) still produces its own persisted FAILED record exactly
    as before; this is only a one-time preflight check in the CLI.
    """

    import httpx

    try:
        response = httpx.get(f"{gateway_url}/health", timeout=5.0)
        response.raise_for_status()
    except Exception as error:
        raise SystemExit(
            f"error: Agent Gateway is not reachable at {gateway_url} "
            f"({type(error).__name__}: {error}).\n"
            "Start it first, in a separate terminal:\n"
            "    uv run uvicorn icab.gateway.app:app --reload\n"
            "then re-run this command (or pass --gateway-url if it is running elsewhere)."
        ) from None


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

    parts = [part.strip() for part in raw.split(",") if part.strip()]

    try:
        return [int(part) for part in parts]
    except ValueError:
        raise SystemExit(
            f"error: --seeds {raw!r} is not a comma-separated list of integers "
            "(e.g. '1,2,3,4,5')."
        ) from None


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

    parser.add_argument("--llm-model", default=None, help="LLM model name (--agent llm only). Default: ICAB_LLM_MODEL from .env.")
    parser.add_argument("--temperature", dest="llm_temperature", type=float, default=None, help="LLM sampling temperature (--agent llm only). Default: 0.0.")
    parser.add_argument("--max-steps", type=int, default=None, help="Max tool-calling loop iterations per run (--agent llm only). Default: unbounded.")
    parser.add_argument("--max-tool-calls", type=int, default=None, help="Max total tool calls per run (--agent llm only). Default: unbounded.")
    parser.add_argument("--max-context-tokens", type=int, default=None, help="Max cumulative LLM token usage per run (--agent llm only). Default: unbounded.")
    parser.add_argument("--max-wall-time", dest="max_wall_time_seconds", type=float, default=None, help="Max wall-clock seconds per run (--agent llm only). Default: unbounded.")

    parser.add_argument("--name", default=None, help="Benchmark/experiment id -- default: auto-generated (never collides). Reusing an existing --name is refused unless --force is also passed.")
    parser.add_argument("--force", action="store_true", help="Allow --name to overwrite a benchmark id that already has persisted results. Off by default -- see docs/benchmark/specification.md.")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL, help=f"Agent Gateway base URL. Default: {DEFAULT_GATEWAY_URL}.")
    parser.add_argument("--results-root", default="results", help="Root directory for raw/traces/evaluations/aggregate/reports/figures. Default: 'results'.")
    parser.add_argument(
        "--validate-architectures",
        action="store_true",
        help=(
            "Run the full architecture connectivity/health check (icab.architecture_health -- "
            "see scripts/check_architecture_health.py) before the benchmark, and refuse to "
            "proceed if any component fails. Off by default (adds real latency: a short real "
            "scenario preparation plus a live check of every architecture)."
        ),
    )

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
        force=args.force,
    )


def main() -> int:
    from pydantic import ValidationError

    from icab.common.config import get_settings

    args = build_parser().parse_args()

    try:
        config = build_benchmark_config(args)
    except ValidationError as error:
        print(f"error: invalid configuration:\n{error}", file=sys.stderr)
        return 2

    settings = get_settings()
    _check_infrastructure_reachable(settings)
    _check_gateway_reachable(args.gateway_url)

    if args.validate_architectures:
        from icab.architecture_health import run_architecture_health_check

        print("Validating architecture connectivity (--validate-architectures)...")
        health_report = run_architecture_health_check(gateway_url=args.gateway_url, settings=settings)
        for result in health_report.results:
            print(f"  {result.component:<15} {result.status}")
        if not health_report.all_passed:
            raise SystemExit(
                f"error: architecture connectivity check failed for: {', '.join(health_report.failed_components)}.\n"
                "Run 'uv run python scripts/check_architecture_health.py' for full details, "
                "fix the failing component(s), then re-run this command."
            )
        print("Architecture connectivity: PASS\n")

    benchmark_runner, mqtt_client, kg_repository = _build_benchmark_runner(args.gateway_url, args.results_root)

    try:
        try:
            with mqtt_client:
                result = benchmark_runner.run(config)
        finally:
            kg_repository.close()
    except (ValueError, KeyError) as error:
        # Configuration-level failures raised by BenchmarkRunner itself
        # (unknown suite/task/architecture, no tasks matched, a
        # benchmark_id collision, ...) -- a clear, one-line message
        # rather than a raw Python traceback as the only explanation.
        # Genuine per-run failures (a specific run's own scenario
        # preparation or agent execution failing) are NOT raised here --
        # those are already caught inside BenchmarkRunner and persisted
        # as their own FAILED ExperimentRecord instead.
        print(f"error: {error}", file=sys.stderr)
        return 2

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
    print(f"qa report:         {result.qa_report_json_path}")
    print(f"                   {result.qa_report_markdown_path}")

    return 1 if result.failed_runs > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
