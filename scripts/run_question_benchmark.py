"""
Runs a selected slice of ONE ISA-95-level question bank
(`icab.benchmark.question_runner.QuestionBenchmarkRunner`) against real
infrastructure -- the Question/QuestionInstance/Repetition entry point,
separate from (but reusing the same execution path as)
`scripts/run_benchmark.py` (tep-v1/tep-v2 suites) and
`scripts/run_context_experiment.py` (single-task context-condition
campaigns).

Results are written under the LEVEL-SCOPED `results/<level>/` tree
(never the old flat `results/`) -- see
`scripts/reset_active_results.py` to start that tree clean first.

Equipment, single-dimension context sweep, 5 repetitions::

    uv run python scripts/run_question_benchmark.py \\
        --level equipment --question-ids Q-d1-qa-current-pressure \\
        --context-combinations C5 --agent llm --repetitions 5

Process Cell, two named questions, two context conditions, two architectures::

    uv run python scripts/run_question_benchmark.py \\
        --level process_cell \\
        --question-ids Q-d4plant-qa-discover-equipment,Q-pc-new-equipment-membership-via-kg \\
        --context-combinations C1+C2,C2+C3 --allow-overshoot --agent llm --repetitions 2
"""

from __future__ import annotations

import argparse
import sys

from icab.benchmark.levels import LEVEL_BENCHMARKS, get_level_benchmark
from icab.benchmark.question_runner import QuestionBenchmarkConfig, QuestionBenchmarkRunner
from icab.questions import QuestionBankRegistry
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--level", required=True, choices=[level.value for level in ISA95Level])
    parser.add_argument("--question-ids", default=None, help="Comma-separated question ids. Default: every question in the level's bank.")
    parser.add_argument("--use-case-ids", default=None, help="Comma-separated use_case ids to restrict to.")
    parser.add_argument("--tags", default=None, help="Comma-separated QuestionCategory tags to restrict to.")

    parser.add_argument("--context-combinations", default=None, help="Comma-separated context combination ids (e.g. 'C5,C2+C3'). Default: each question's own hypothesized_required_context.")
    parser.add_argument("--allow-overshoot", action="store_true")
    parser.add_argument("--scenario-ids", default=None, help="Comma-separated scenario ids to restrict to. Default: every scenario each question has a realization for.")

    parser.add_argument("--agent", default="llm")
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--temperature", dest="llm_temperature", type=float, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    parser.add_argument("--max-context-tokens", type=int, default=None)
    parser.add_argument("--max-wall-time", dest="max_wall_time_seconds", type=float, default=None)

    parser.add_argument("--repetitions", type=int, default=1, help="Repetitions per (question, scenario, context condition, architecture) instance. Not hard-coded -- configurable.")
    parser.add_argument("--seeds", default=None)
    parser.add_argument(
        "--repetition-mode",
        default="exact",
        choices=["exact", "controlled_variation"],
        help="'exact': identical instance repeated (stochasticity/reproducibility). 'controlled_variation': deliberately varying --scenario-ids across the SAME question (robustness/generalization).",
    )

    parser.add_argument("--name", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)

    return parser


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def build_question_benchmark_config(args: argparse.Namespace) -> QuestionBenchmarkConfig:
    return QuestionBenchmarkConfig(
        question_ids=_csv(args.question_ids),
        use_case_ids=_csv(args.use_case_ids),
        tags=_csv(args.tags),
        context_combination_ids=_csv(args.context_combinations),
        allow_overshoot=args.allow_overshoot,
        scenario_ids=_csv(args.scenario_ids),
        agent=args.agent,
        llm_model=args.llm_model,
        llm_temperature=args.llm_temperature,
        max_steps=args.max_steps,
        max_tool_calls=args.max_tool_calls,
        max_context_tokens=args.max_context_tokens,
        max_wall_time_seconds=args.max_wall_time_seconds,
        repetitions=args.repetitions,
        seeds=_parse_seeds(args.seeds),
        repetition_mode=args.repetition_mode,
        name=args.name,
        force=args.force,
    )


def main() -> int:
    from pydantic import ValidationError

    from icab.common.config import get_settings

    args = build_parser().parse_args()
    level = ISA95Level(args.level)
    definition = get_level_benchmark(level)

    if not definition.executable:
        print(
            f"error: {definition.benchmark_id} ({level.value}) is not executable: {definition.coverage_note}",
            file=sys.stderr,
        )
        return 2

    try:
        config = build_question_benchmark_config(args)
    except ValidationError as error:
        print(f"error: invalid configuration:\n{error}", file=sys.stderr)
        return 2

    settings = get_settings()
    _check_infrastructure_reachable(settings)
    _check_gateway_reachable(args.gateway_url)

    benchmark_runner, mqtt_client, kg_repository = _build_benchmark_runner(args.gateway_url, str(definition.results_root))

    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)

    runner = QuestionBenchmarkRunner(
        definition=definition,
        experiment_runner=benchmark_runner.experiment_runner,
        question_registry=question_registry,
        use_case_registry=use_case_registry,
        task_registry=task_registry,
        scenario_registry=scenario_registry,
        experiment_store=benchmark_runner.experiment_store,
    )

    try:
        try:
            with mqtt_client:
                result = runner.run(config)
        finally:
            kg_repository.close()
    except (ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"campaign_id:       {result.campaign_id}")
    print(f"benchmark_id:      {result.benchmark_id}   isa95_level: {result.isa95_level}")
    print(f"instances:         total={result.total_selected_instances} executed={result.executed_instances}")
    print(f"runs:              total={result.total_runs} successful={result.successful_runs} failed={result.failed_runs}")
    print(f"manifest:          {result.manifest_path}")
    print()
    for outcome in result.outcomes:
        marker = "RAN" if outcome.executed else "skip"
        archs = "+".join(outcome.resolved_architectures) if outcome.resolved_architectures else "-"
        print(f"  [{marker:4}] {outcome.question_id:<45} {outcome.scenario_id:<35} {outcome.context_combination_id:<20} {outcome.resolution_status:<15} arch={archs}")

    return 1 if result.failed_runs > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
