"""
ICAB v2 (context-requirement experimentation): runs a chosen SET of
context conditions against ONE task, using the SAME real infrastructure
`scripts/run_benchmark.py` uses (mirrors its preflight checks and
construction pattern) -- see `icab.benchmark.context_experiment` for the
orchestration itself.

Every run this produces is persisted under the same `results/{raw,traces,
evaluations}/` layout `run_benchmark.py` uses, so `scripts/icab_v2_cli.py
analyze-*`/`generate-profiles`/the new `matrix-*` commands pick it up
automatically -- this script does not write its own separate report
format.

Single-dimension sweep, resolved automatically, only EXACT conditions run::

    uv run python scripts/run_context_experiment.py \\
        --suite tep-v2 --task d4plant-investigation-open-ended \\
        --design single --agent baseline --seeds 1

Ablation from this task's own full achievable context, including
OVERSHOOT steps (labeled as such, never silently treated as exact)::

    uv run python scripts/run_context_experiment.py \\
        --suite tep-v2 --task d2cooling-diagnosis-heat-transfer-category \\
        --design ablation --allow-overshoot --agent llm --seeds 1

Targeted, explicit combinations::

    uv run python scripts/run_context_experiment.py \\
        --suite tep-v2 --task d4plant-investigation-open-ended \\
        --design targeted --targets C5,C2+C5 --agent llm --seeds 1

Replay every combination already tested for this task::

    uv run python scripts/run_context_experiment.py \\
        --suite tep-v2 --task d4plant-investigation-open-ended \\
        --design replay --agent llm --seeds 1
"""

from __future__ import annotations

import argparse
import sys

from icab.benchmark import ContextExperimentConfig, ContextExperimentRunner
from icab.scenarios import BenchmarkScenarioRegistry
from icab.usecases import IndustrialUseCaseRegistry

# Reuse run_benchmark.py's own preflight checks/infrastructure wiring
# rather than re-implementing them -- resolvable because Python puts this
# script's own directory (scripts/) at the front of sys.path when it is
# run directly (`uv run python scripts/run_context_experiment.py`).
from run_benchmark import (
    DEFAULT_GATEWAY_URL,
    _build_benchmark_runner,
    _check_gateway_reachable,
    _check_infrastructure_reachable,
    _parse_seeds,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--suite", required=True, help="Registered benchmark suite, e.g. 'tep-v2'.")
    parser.add_argument("--task", dest="task_id", required=True, help="Which BenchmarkTask to run every condition against.")

    parser.add_argument("--design", required=True, choices=["single", "pairwise", "progressive", "targeted", "ablation", "replay"])
    parser.add_argument("--targets", default=None, help="TARGETED only: comma-separated combination ids, e.g. 'C5,C2+C5'.")
    parser.add_argument("--baseline", default=None, help="ABLATION only: combination id to ablate from. Default: this task's own architectures, used together.")
    parser.add_argument("--progressive-order", default=None, help="PROGRESSIVE only: comma-separated permutation of C1..C7. Default: canonical order.")
    parser.add_argument("--allow-overshoot", action="store_true", help="Also run conditions that can only be realized as a superset of the requested dimensions (labeled 'overshoot', never silently treated as exact). Off by default.")

    parser.add_argument("--agent", default="llm", help="'baseline' or 'llm' -- see run_benchmark.py --agent.")
    parser.add_argument("--seeds", default=None, help="Comma-separated seed overrides, e.g. '1,2,3'.")
    parser.add_argument("--repetitions", type=int, default=1)

    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--temperature", dest="llm_temperature", type=float, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    parser.add_argument("--max-context-tokens", type=int, default=None)
    parser.add_argument("--max-wall-time", dest="max_wall_time_seconds", type=float, default=None)

    parser.add_argument("--name", default=None, help="Campaign id -- default: auto-generated (never collides).")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--results-root", default="results")
    parser.add_argument("--usecases-dir", default="configs/usecases", help="Directory of IndustrialUseCase YAMLs, for not_applicable classification. Pass '' to disable use-case scoping.")

    return parser


def build_context_experiment_config(args: argparse.Namespace) -> ContextExperimentConfig:
    return ContextExperimentConfig(
        suite=args.suite,
        task_id=args.task_id,
        design=args.design,
        targets=[t.strip() for t in args.targets.split(",")] if args.targets else None,
        baseline=args.baseline,
        progressive_order=[d.strip() for d in args.progressive_order.split(",")] if args.progressive_order else None,
        allow_overshoot=args.allow_overshoot,
        agent=args.agent,
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
        config = build_context_experiment_config(args)
    except ValidationError as error:
        print(f"error: invalid configuration:\n{error}", file=sys.stderr)
        return 2

    settings = get_settings()
    _check_infrastructure_reachable(settings)
    _check_gateway_reachable(args.gateway_url)

    benchmark_runner, mqtt_client, kg_repository = _build_benchmark_runner(args.gateway_url, args.results_root)

    use_case_registry = None
    if args.usecases_dir:
        try:
            use_case_registry = IndustrialUseCaseRegistry(
                args.usecases_dir, scenario_registry=BenchmarkScenarioRegistry("configs/benchmark/scenarios")
            )
        except (FileNotFoundError, NotADirectoryError):
            print(f"warning: --usecases-dir {args.usecases_dir!r} not found -- not_applicable classification disabled.", file=sys.stderr)

    context_runner = ContextExperimentRunner(
        experiment_runner=benchmark_runner.experiment_runner,
        experiment_store=benchmark_runner.experiment_store,
        use_case_registry=use_case_registry,
    )

    try:
        try:
            with mqtt_client:
                result = context_runner.run(config)
        finally:
            kg_repository.close()
    except (ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"campaign_id:       {result.campaign_id}")
    print(f"suite:             {result.suite}   task: {result.task_id}")
    print(f"use_case:          {result.use_case_id or '(none)'}   isa95_level: {result.isa95_level or '(none)'}")
    print(f"design:            {result.design}")
    print(
        f"conditions:        total={result.total_conditions} executed={result.executed_conditions} "
        f"not_applicable={result.not_applicable_conditions} unrealizable={result.unrealizable_conditions} "
        f"overshoot_skipped={result.overshoot_skipped_conditions}"
    )
    print(f"runs:              total={result.total_runs} successful={result.successful_runs} failed={result.failed_runs}")
    print()
    for condition in result.conditions:
        marker = "RAN" if condition.executed else "skip"
        archs = "+".join(condition.resolved_architectures) if condition.resolved_architectures else "-"
        print(f"  [{marker:4}] {condition.combination_id:<20} {condition.resolution_status:<15} arch={archs:<30} {condition.reason}")

    return 1 if result.failed_runs > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
