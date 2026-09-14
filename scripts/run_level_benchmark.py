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

User-facing question inspection / dry-run / standalone export (no
redesign of the question suite or execution path -- these sit ABOVE the
existing runner, reusing it as-is; see docs/benchmark/specification-v3.md
"Standalone benchmark execution and export"):

    uv run python scripts/run_level_benchmark.py --level equipment --list-questions
    uv run python scripts/run_level_benchmark.py --level equipment --show-question <question_id>
    uv run python scripts/run_level_benchmark.py --level equipment --dry-run --repetitions 10
    uv run python scripts/run_level_benchmark.py --level equipment --repetitions 10 --name my-campaign --output benchmark_exports
    uv run python scripts/run_level_benchmark.py --level equipment --repetitions 10 --name my-campaign --resume --output benchmark_exports

NOTE on script naming: `scripts/run_benchmark.py` already exists (the
pre-existing tep-v1/tep-v2 SUITE runner, M13-D) -- this script is
deliberately NOT a second `run_benchmark.py`. It is the ICAB v3
50-question-per-level benchmark's own runner (built for the 3,000-
execution milestone) and is now ALSO the standalone question-inspection/
dry-run/resumable-execution/export entry point the ICAB export milestone
asked for, rather than introducing a third, confusingly-named script.
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
from icab.benchmark.levels import get_level_benchmark
from icab.benchmark.question_runner import QuestionBenchmarkConfig, QuestionBenchmarkRunner
from icab.experiments import ExperimentResultStore
from icab.export import CampaignExportWriter, build_canonical_record, validate_export
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
    parser.add_argument("--force", action="store_true", help="Start a campaign even if --name already has persisted results (overwrites nothing; new runs are added under the same campaign id). Mutually exclusive in effect with --resume.")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)

    parser.add_argument("--list-questions", action="store_true", help="List the question bank for --level (id + text), then exit. No gateway/LLM call. Requires --level.")
    parser.add_argument("--show-question", metavar="QUESTION_ID", default=None, help="Show one question's full existing metadata for --level, then exit. No gateway/LLM call. Requires --level.")
    parser.add_argument("--dry-run", action="store_true", help="Show the exact execution plan for --level (questions, repetitions, planned executions, resolved config) without making any LLM call. Requires --level.")
    parser.add_argument("--resume", action="store_true", help="Continue a previously started campaign (--name) -- executions whose deterministic run_id already has a persisted record are skipped, never duplicated.")
    parser.add_argument("--output", default="benchmark_exports", help="Standalone export root -- separate from results/, never overwrites a previous campaign's export. Default: benchmark_exports")
    parser.add_argument("--no-export", action="store_true", help="Skip writing the standalone benchmark_exports/ dataset after execution (results/ is still written as normal).")

    return parser


def _build_level_context(level: str):
    """(definition, scenario_registry, task_registry, use_case_registry, question_registry) -- shared by every mode below."""

    definition = get_level_benchmark(ISA95Level(level))
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
    question_registry = QuestionBankRegistry(definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)
    return definition, scenario_registry, task_registry, use_case_registry, question_registry


def _resolve_question_ids(args: argparse.Namespace, question_registry: QuestionBankRegistry, level: str) -> list[str] | None:
    question_ids = [q.strip() for q in args.question_ids.split(",")] if args.question_ids else None
    if question_ids is None and len(question_registry) != TARGET_QUESTIONS_PER_LEVEL:
        raise SystemExit(
            f"error: {level} has {len(question_registry)} questions, not exactly {TARGET_QUESTIONS_PER_LEVEL} -- "
            "refusing to start the standard campaign. Pass --question-ids to run a smaller, explicitly-scoped subset instead."
        )
    return question_ids


def _build_config(args: argparse.Namespace, level: str, question_ids: list[str] | None) -> QuestionBenchmarkConfig:
    return QuestionBenchmarkConfig(
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
        resume=args.resume,
    )


def _list_questions(level: str, args: argparse.Namespace) -> int:
    definition, _scenario_registry, _task_registry, _use_case_registry, question_registry = _build_level_context(level)
    question_ids = _resolve_question_ids(args, question_registry, level)
    questions = question_registry.for_level(ISA95Level(level))
    if question_ids is not None:
        wanted = set(question_ids)
        questions = [q for q in questions if q.question_id in wanted]
    questions.sort(key=lambda q: q.question_id)

    planned_executions = len(questions) * args.repetitions

    print(f"ISA-95 level: {level}")
    print(f"Benchmark id: {definition.benchmark_id}")
    print(f"Questions: {len(questions)}")
    print(f"Repetitions per question: {args.repetitions}")
    print(f"Planned executions: {planned_executions}")
    print()
    for i, question in enumerate(questions, start=1):
        print(f"{i:3d}. {question.question_id}  -- {question.question_text}")
    return 0


def _show_question(level: str, question_id: str) -> int:
    _definition, _scenario_registry, task_registry, _use_case_registry, question_registry = _build_level_context(level)
    try:
        question = question_registry.get(question_id)
    except KeyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"question_id:            {question.question_id}")
    print(f"isa95_level:             {question.isa95_level.value}")
    print(f"use_case_id:             {question.use_case_id}")
    print(f"question_text:           {question.question_text}")
    print(f"objective:               {question.objective}")
    print(f"expected_answer_type:    {question.expected_answer_type.value}")
    print(f"difficulty:              {question.difficulty.value}")
    print(f"difficulty_factors:      {question.difficulty_factors.model_dump()}")
    print(f"tags:                    {[t.value for t in question.tags]}")
    print(f"hypothesized_required_context: {[d.value for d in question.hypothesized_required_context]}")
    print(f"expected_evidence_description:  {question.expected_evidence_description}")
    print(f"compatible_scenarios:    {question.compatible_scenarios}")
    print(f"realizations:            {question.realizations}")
    print(f"version:                 {question.version}")
    print(f"validation_status:       {question.validation_status.value}")
    print(f"provenance:              {question.provenance}")

    print()
    print("Ground truth (per realized scenario -- researcher-only, never shown to the agent):")
    for scenario_id, task_id in sorted(question.realizations.items()):
        task = task_registry.get(task_id)
        print(f"  [{scenario_id}] task={task_id}")
        print(f"    conclusion:              {task.ground_truth.conclusion}")
        print(f"    root_cause_disturbance:  {task.ground_truth.root_cause_disturbance}")
        print(f"    affected_measurements:   {task.ground_truth.affected_measurements}")
        print(f"    affected_equipment:      {task.ground_truth.affected_equipment}")
        print(f"    expected_relationships:  {task.ground_truth.expected_relationships}")
        print(f"    expected_evidence:       {task.ground_truth.expected_evidence}")
        print(f"    available_architectures: {task.available_architectures}")
        print(f"    binding_scores:          {task.evaluation_criteria.binding_scores} (pass_threshold={task.evaluation_criteria.pass_threshold})")
    return 0


def _dry_run(level: str, args: argparse.Namespace) -> int:
    definition, scenario_registry, task_registry, use_case_registry, question_registry = _build_level_context(level)
    question_ids = _resolve_question_ids(args, question_registry, level)
    config = _build_config(args, level, question_ids)

    # experiment_runner=None: .plan() never touches it -- it makes no
    # gateway/agent/LLM call and never writes to experiment_store.
    runner = QuestionBenchmarkRunner(
        definition=definition,
        experiment_runner=None,  # type: ignore[arg-type]
        question_registry=question_registry,
        use_case_registry=use_case_registry,
        task_registry=task_registry,
        scenario_registry=scenario_registry,
        experiment_store=ExperimentResultStore(root=definition.results_root),
    )

    try:
        plan = runner.plan(config)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"DRY RUN -- no LLM call made, nothing persisted.")
    print(f"ISA-95 level:        {plan.isa95_level}")
    print(f"Benchmark id:        {plan.benchmark_id}")
    print(f"Campaign id:         {plan.campaign_id}")
    print(f"Agent:               {plan.agent}")
    print(f"LLM model:           {plan.llm_model}")
    print(f"Repetitions:         {plan.repetitions} (mode: {plan.repetition_mode})")
    print(f"Seeds:               {plan.seeds}")
    print(f"Planned instances:   {plan.planned_instances}")
    print(f"Planned executions:  {plan.planned_executions}")
    print()
    skipped = [o for o in plan.outcomes if o.instance_id is None]
    print(f"Resolvable outcomes: {len(plan.outcomes) - len(skipped)} / {len(plan.outcomes)} (skipped: {len(skipped)})")
    for outcome in plan.outcomes:
        marker = "OK  " if outcome.instance_id is not None else "SKIP"
        archs = "+".join(outcome.resolved_architectures) if outcome.resolved_architectures else "(none)"
        print(f"  [{marker}] {outcome.question_id:30s} scenario={outcome.scenario_id:30s} arch={archs:20s} {outcome.reason}")
    return 0


def _export_campaign(
    level: str,
    definition,
    result,
    question_registry: QuestionBankRegistry,
    task_registry: BenchmarkTaskRegistry,
    question_ids: list[str] | None,
    args: argparse.Namespace,
):
    from icab.benchmark.config import get_git_commit
    from icab.experiments import ExperimentResultStore

    store = ExperimentResultStore(root=definition.results_root)
    canonical_records = []
    for outcome in result.outcomes:
        if not outcome.run_ids:
            continue
        question = question_registry.get(outcome.question_id) if outcome.question_id in question_registry.list_ids() else None
        task = None
        if question is not None and outcome.scenario_id in question.realizations:
            task = task_registry.get(question.realizations[outcome.scenario_id])
        for run_id in outcome.run_ids:
            record = store.load_record(run_id)
            trace = store.load_trace(run_id)
            canonical_records.append(
                build_canonical_record(
                    record,
                    trace,
                    question=question,
                    task=task,
                    campaign_id=result.campaign_id,
                    benchmark_name=definition.benchmark_id,
                    benchmark_version=definition.question_bank_version,
                )
            )

    planned_questions = list(question_registry)
    if question_ids is not None:
        wanted = set(question_ids)
        planned_questions = [q for q in planned_questions if q.question_id in wanted]
    else:
        planned_questions = question_registry.for_level(ISA95Level(level))

    manifest_extra = {
        "benchmark_name": definition.benchmark_id,
        "benchmark_version": definition.question_bank_version,
        "repetitions": args.repetitions,
        "repetition_mode": RepetitionMode.EXACT.value,
        "agent": args.agent,
        "llm_model": args.llm_model,
        "llm_temperature": args.llm_temperature,
        "max_steps": args.max_steps,
        "seeds": _parse_seeds(args.seeds),
        "git_commit": get_git_commit(),
        "results_root": str(definition.results_root),
    }

    writer = CampaignExportWriter(output_root=args.output)
    campaign_dir = writer.write(
        isa95_level=level,
        campaign_id=result.campaign_id,
        records=canonical_records,
        planned_questions=planned_questions,
        manifest_extra=manifest_extra,
    )

    report = validate_export(campaign_dir)
    print(f"[{level}] exported {len(canonical_records)} execution(s) -> {campaign_dir}")
    if report.is_valid:
        print(f"[{level}] export validation: OK")
    else:
        print(f"[{level}] export validation ISSUES:", file=sys.stderr)
        for issue in report.issues:
            print(f"  - {issue}", file=sys.stderr)

    return campaign_dir


def _run_one_level(level: str, args: argparse.Namespace) -> tuple[int, int]:
    """Returns (successful_runs, failed_runs)."""

    definition, scenario_registry, task_registry, use_case_registry, question_registry = _build_level_context(level)
    question_ids = _resolve_question_ids(args, question_registry, level)

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

    config = _build_config(args, level, question_ids)

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

    if not args.no_export:
        _export_campaign(level, definition, result, question_registry, task_registry, question_ids, args)

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

    # Question inspection / dry-run -- no gateway/LLM call, no
    # results/ or benchmark_exports/ write. Requires a single --level
    # (these operate on one level's own question bank, not --all).
    inspection_flags = [args.list_questions, bool(args.show_question), args.dry_run]
    if any(inspection_flags):
        if args.level is None:
            print("error: --list-questions/--show-question/--dry-run require --level (not --all/--check-only).", file=sys.stderr)
            return 2
        if args.list_questions:
            return _list_questions(args.level, args)
        if args.show_question:
            return _show_question(args.level, args.show_question)
        return _dry_run(args.level, args)

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
