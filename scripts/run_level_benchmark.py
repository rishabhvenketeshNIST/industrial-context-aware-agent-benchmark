"""
Runs the STANDARD ICAB v3 50-question x 10-repetition benchmark for one
(or every) ISA-95 level -- the canonical baseline score, held distinct
from ad-hoc research experiments (icab.benchmark.context_experiment /
scripts/run_context_experiment.py), which vary context/architecture/
scenario freely and are NEVER what this script measures.

The "standard benchmark condition" per question is fixed and EXACT
(same scenario, same resolved architecture arm, same agent config
repeated N times, per icab.questions.RepetitionMode.EXACT) -- the
architecture arm is resolved from each question's own
`hypothesized_required_context`, exactly like `icab.benchmark
.context_experiment` already does for research campaigns, just applied
uniformly across the whole level's bank rather than one hand-picked
question.

Refuses to even start a level's campaign unless its question bank has
EXACTLY 50 questions (`icab.benchmark.completeness
.TARGET_QUESTIONS_PER_LEVEL`) -- a smaller/larger bank is a
configuration error, not something to silently run anyway.

Equipment, 50 questions x 10 repetitions::

    uv run python scripts/run_level_benchmark.py --level equipment --repetitions 10

Every level, one command (large -- see docs/benchmark/specification-v3.md
for realistic wall-clock expectations; supports resuming a partial
campaign level-by-level)::

    uv run python scripts/run_level_benchmark.py --all --repetitions 10

Completeness check only, no execution::

    uv run python scripts/run_level_benchmark.py --check-only
"""

from __future__ import annotations

import argparse
import sys

from icab.benchmark.completeness import (
    TARGET_QUESTIONS_PER_LEVEL,
    SuiteCompletenessReport,
    check_level_completeness,
    render_completeness_table,
)
from icab.benchmark.levels import LEVEL_BENCHMARKS, get_level_benchmark
from icab.benchmark.question_runner import QuestionBenchmarkConfig, QuestionBenchmarkRunner
from icab.questions import QuestionBankRegistry
from icab.questions.instance import RepetitionMode
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.isa95 import ISA95Level
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

from run_benchmark import (
    DEFAULT_GATEWAY_URL,
    _build_benchmark_runner,
    _check_gateway_reachable,
    _check_infrastructure_reachable,
    _parse_seeds,
)

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"

ALL_LEVELS = [level.value for level in ISA95Level]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    level_group = parser.add_mutually_exclusive_group(required=True)
    level_group.add_argument("--level", choices=ALL_LEVELS, help="Run the standard benchmark for one ISA-95 level.")
    level_group.add_argument("--all", action="store_true", help="Run the standard benchmark for all six levels, in order.")
    level_group.add_argument("--check-only", action="store_true", help="Only report completeness against already-persisted results/<level>/ -- no execution.")

    parser.add_argument("--repetitions", type=int, default=10, help="Repetitions per question. Default: 10 (the standard campaign target).")
    parser.add_argument("--question-ids", default=None, help="Restrict to these comma-separated question ids (skips the 50-question preflight check -- for a smaller test run, not the standard campaign).")
    parser.add_argument("--seeds", default=None)
    parser.add_argument(
        "--strict-exact-context-only",
        action="store_true",
        help=(
            "By default this runner resolves EACH question's own designated architecture "
            "even when it overshoots that question's hypothesized_required_context (the "
            "normal, expected case here -- see docs/benchmark/specification-v3.md). Pass "
            "this to instead SKIP any question whose designated architecture cannot realize "
            "its hypothesized context exactly -- will skip most questions, not the standard campaign."
        ),
    )

    parser.add_argument("--agent", default="llm")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--temperature", dest="llm_temperature", type=float, default=None)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    parser.add_argument("--max-context-tokens", type=int, default=None)
    parser.add_argument("--max-wall-time", dest="max_wall_time_seconds", type=float, default=None)

    parser.add_argument("--name", default=None, help="Campaign id prefix. Default: auto-generated per level.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)

    return parser


def _run_one_level(level: str, args: argparse.Namespace) -> tuple[int, int]:
    """Returns (successful_runs, failed_runs)."""

    definition = get_level_benchmark(ISA95Level(level))
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)

    question_ids = [q.strip() for q in args.question_ids.split(",")] if args.question_ids else None

    if question_ids is None and len(question_registry) != TARGET_QUESTIONS_PER_LEVEL:
        raise SystemExit(
            f"error: {level} has {len(question_registry)} questions, not exactly {TARGET_QUESTIONS_PER_LEVEL} -- "
            "refusing to start the standard campaign. Pass --question-ids to run a smaller, explicitly-scoped subset instead."
        )

    benchmark_runner, mqtt_client, kg_repository = _build_benchmark_runner(args.gateway_url, str(definition.results_root))

    runner = QuestionBenchmarkRunner(
        definition=definition,
        experiment_runner=benchmark_runner.experiment_runner,
        question_registry=question_registry,
        use_case_registry=use_case_registry,
        task_registry=task_registry,
        scenario_registry=scenario_registry,
        experiment_store=benchmark_runner.experiment_store,
    )

    config = QuestionBenchmarkConfig(
        question_ids=question_ids,
        allow_overshoot=not args.strict_exact_context_only,
        agent=args.agent,
        llm_model=args.llm_model,
        llm_temperature=args.llm_temperature,
        max_steps=args.max_steps,
        max_tool_calls=args.max_tool_calls,
        max_context_tokens=args.max_context_tokens,
        max_wall_time_seconds=args.max_wall_time_seconds,
        repetitions=args.repetitions,
        seeds=_parse_seeds(args.seeds),
        repetition_mode=RepetitionMode.EXACT.value,
        name=f"{args.name}-{level}" if args.name else None,
        force=args.force,
    )

    try:
        try:
            with mqtt_client:
                result = runner.run(config)
        finally:
            kg_repository.close()
    except (ValueError, KeyError) as error:
        print(f"error running {level}: {error}", file=sys.stderr)
        return 0, 0

    print(f"[{level}] campaign_id={result.campaign_id} instances={result.executed_instances}/{result.total_selected_instances} "
          f"runs={result.total_runs} successful={result.successful_runs} failed={result.failed_runs}")

    return result.successful_runs, result.failed_runs


def _completeness_for_level(level: str) -> "LevelCompletenessReport":  # noqa: F821
    from icab.experiments import ExperimentResultStore

    definition = get_level_benchmark(ISA95Level(level))
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)

    store = ExperimentResultStore(root=definition.results_root)
    records = [store.load_record(rid) for rid in store.list_run_ids()]

    return check_level_completeness(level, question_registry, records, benchmark_id=definition.benchmark_id)


def main() -> int:
    from pydantic import ValidationError

    args = build_parser().parse_args()

    if args.check_only:
        report = SuiteCompletenessReport(levels=[_completeness_for_level(level) for level in ALL_LEVELS])
        print(render_completeness_table(report))
        return 0 if report.is_complete else 1

    from icab.common.config import get_settings

    settings = get_settings()
    _check_infrastructure_reachable(settings)
    _check_gateway_reachable(args.gateway_url)

    levels = ALL_LEVELS if args.all else [args.level]

    total_successful = total_failed = 0
    try:
        for level in levels:
            successful, failed = _run_one_level(level, args)
            total_successful += successful
            total_failed += failed
    except ValidationError as error:
        print(f"error: invalid configuration:\n{error}", file=sys.stderr)
        return 2

    print()
    report = SuiteCompletenessReport(levels=[_completeness_for_level(level) for level in ALL_LEVELS])
    print(render_completeness_table(report))

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
