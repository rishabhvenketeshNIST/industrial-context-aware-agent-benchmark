"""
ICAB v2: the exploration/analysis CLI -- list ISA-95 levels/use cases/
context dimensions/combinations, validate architecture connectivity,
and run the context necessity/sufficiency/composition/representation/
efficiency analyses over already-persisted results.

This is deliberately SEPARATE from `scripts/run_benchmark.py` (which
still runs the actual benchmark, tep-v1 and tep-v2 alike -- see its own
`--suite tep-v2`) and from `scripts/generate_report.py` (the existing
M12 aggregate-report generator, unchanged and still the way to produce a
grouped aggregate report). This script is the exploration/analysis layer
ICAB v2 adds ON TOP of that existing infrastructure -- it makes no
simulator/gateway/LLM call itself, only reading already-persisted
`results/{raw,evaluations}/` records via `ExperimentResultStore`
(same convention `scripts/generate_report.py` already uses).

Examples::

    uv run python scripts/icab_v2_cli.py list-isa95-levels
    uv run python scripts/icab_v2_cli.py list-use-cases
    uv run python scripts/icab_v2_cli.py list-use-cases --level equipment
    uv run python scripts/icab_v2_cli.py list-context-dimensions
    uv run python scripts/icab_v2_cli.py list-context-combinations --cardinality 2
    uv run python scripts/icab_v2_cli.py validate-architectures
    uv run python scripts/icab_v2_cli.py validate-faults
    uv run python scripts/icab_v2_cli.py analyze-necessity --use-case eq-value-and-relationship-combination
    uv run python scripts/icab_v2_cli.py analyze-sufficiency --use-case eq-value-and-relationship-combination
    uv run python scripts/icab_v2_cli.py analyze-composition --use-case eq-value-and-relationship-combination
    uv run python scripts/icab_v2_cli.py analyze-representation --use-case eq-value-and-relationship-combination
    uv run python scripts/icab_v2_cli.py generate-profiles --out results/reports/context-design-profiles.json
"""

from __future__ import annotations

import argparse
import json
import sys

USECASES_DIR = "configs/usecases"
SCENARIOS_DIR = "configs/benchmark/scenarios"


def _use_case_registry():
    from icab.scenarios import BenchmarkScenarioRegistry
    from icab.usecases import IndustrialUseCaseRegistry

    return IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=BenchmarkScenarioRegistry(SCENARIOS_DIR))


def _load_v2_records(results_root: str, suite: str) -> list:
    from icab.experiments import ExperimentResultStore

    store = ExperimentResultStore(root=results_root)
    records = []
    for run_id in store.list_run_ids():
        record = store.load_record(run_id)
        if record.config.suite == suite:
            records.append(record)
    return records


def cmd_list_isa95_levels(args: argparse.Namespace) -> int:
    from icab.usecases import ISA95_LEVEL_COVERAGE_NOTES, ISA95Level

    registry = _use_case_registry()
    for level in ISA95Level:
        n = len(registry.for_level(level))
        print(f"{level.value:<12} use_cases={n}")
        print(f"             {ISA95_LEVEL_COVERAGE_NOTES[level]}")
    return 0


def cmd_list_use_cases(args: argparse.Namespace) -> int:
    from icab.usecases import ISA95Level

    registry = _use_case_registry()
    level_filter = ISA95Level(args.level) if args.level else None

    for use_case in sorted(registry, key=lambda u: u.use_case_id):
        if level_filter is not None and use_case.isa95_level != level_filter:
            continue
        dims = "+".join(d.value for d in use_case.required_context)
        print(f"{use_case.use_case_id:<45} [{use_case.isa95_level.value:<12}] required=[{dims}]  {use_case.name}")
    return 0


def cmd_list_context_dimensions(args: argparse.Namespace) -> int:
    from icab.tasks.context_dimensions import CONTEXT_DIMENSION_ARCHITECTURES, CONTEXT_DIMENSION_LABELS, ContextDimension

    for dimension in ContextDimension:
        architectures = ", ".join(sorted(CONTEXT_DIMENSION_ARCHITECTURES[dimension]))
        print(f"{dimension.value}  {CONTEXT_DIMENSION_LABELS[dimension]:<15} architectures=[{architectures}]")
    return 0


def cmd_list_context_combinations(args: argparse.Namespace) -> int:
    from icab.tasks.context_combinations import ALL_CONTEXT_COMBINATIONS

    combinations = ALL_CONTEXT_COMBINATIONS
    if args.cardinality is not None:
        combinations = [c for c in combinations if c.cardinality == args.cardinality]

    for combo in combinations:
        print(f"{combo.combination_id:<20} cardinality={combo.cardinality}  {combo.name}")
    print(f"\n{len(combinations)} combination(s) shown (127 total exist).")
    return 0


def cmd_validate_architectures(args: argparse.Namespace) -> int:
    from icab.architecture_health import run_architecture_health_check
    from icab.common.config import get_settings

    gateway_url = None if args.skip_gateway else args.gateway_url
    report = run_architecture_health_check(gateway_url=gateway_url, settings=get_settings())

    for result in report.results:
        print(f"{result.component:<15} {result.status}")
        if result.status != "PASS":
            print(f"    {result.failure_reason}")
    print(f"\nOverall: {'PASS' if report.all_passed else 'FAIL'}")
    return 0 if report.all_passed else 1


def cmd_validate_faults(args: argparse.Namespace) -> int:
    from icab.tep.faults import load_fault_catalog

    catalog = load_fault_catalog()
    verified = catalog.verified()
    print(f"{len(catalog.entries)} disturbance(s) in catalog; {len(verified)} empirically_verified (benchmark-ready).")
    for entry in catalog.entries:
        tier = "empirically_verified" if entry.empirically_verified else ("icab_injectable" if entry.icab_injectable else "simulator_supported")
        print(f"  {entry.disturbance:<10} {tier}")
    return 0


def _analysis_setup(args: argparse.Namespace):
    use_case = _use_case_registry().get(args.use_case)
    records = _load_v2_records(args.results_root, args.suite)
    return use_case, records


def cmd_analyze_necessity(args: argparse.Namespace) -> int:
    from icab.analysis import analyze_context_necessity

    use_case, records = _analysis_setup(args)
    report = analyze_context_necessity(records, use_case, metric=args.metric)
    print(report.model_dump_json(indent=2))
    return 0


def cmd_analyze_sufficiency(args: argparse.Namespace) -> int:
    from icab.analysis import find_minimum_sufficient_context

    use_case, records = _analysis_setup(args)
    report = find_minimum_sufficient_context(records, use_case)
    print(report.model_dump_json(indent=2))
    return 0


def cmd_analyze_composition(args: argparse.Namespace) -> int:
    from icab.analysis import analyze_context_composition

    use_case, records = _analysis_setup(args)
    report = analyze_context_composition(records, use_case, metric=args.metric)
    print(report.model_dump_json(indent=2))
    return 0


def cmd_analyze_representation(args: argparse.Namespace) -> int:
    from icab.analysis import analyze_representation

    use_case, records = _analysis_setup(args)
    report = analyze_representation(records, use_case)
    print(report.model_dump_json(indent=2))
    return 0


def cmd_analyze_architecture(args: argparse.Namespace) -> int:
    from icab.analysis import analyze_context_efficiency

    use_case, records = _analysis_setup(args)
    report = analyze_context_efficiency(records, use_case)
    print(report.model_dump_json(indent=2))
    return 0


def cmd_generate_profiles(args: argparse.Namespace) -> int:
    from icab.analysis import build_context_design_profile

    registry = _use_case_registry()
    records = _load_v2_records(args.results_root, args.suite)

    profiles = {}
    for use_case in registry:
        matching = [r for r in records if r.config.use_case_id == use_case.use_case_id]
        if not matching:
            continue
        profiles[use_case.use_case_id] = build_context_design_profile(records, use_case).model_dump()

    payload = json.dumps(profiles, indent=2)
    if args.out:
        from pathlib import Path

        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        print(f"Wrote {len(profiles)} profile(s) to {path}")
    else:
        print(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-isa95-levels", help="List every ISA-95 level and its real use-case coverage.").set_defaults(func=cmd_list_isa95_levels)

    p = subparsers.add_parser("list-use-cases", help="List every registered IndustrialUseCase.")
    p.add_argument("--level", default=None, choices=["enterprise", "site", "area", "work_center", "process_cell", "equipment"])
    p.set_defaults(func=cmd_list_use_cases)

    subparsers.add_parser("list-context-dimensions", help="List the seven locked context dimensions (C1-C7).").set_defaults(func=cmd_list_context_dimensions)

    p = subparsers.add_parser("list-context-combinations", help="List the 127 non-empty context-dimension combinations.")
    p.add_argument("--cardinality", type=int, default=None, choices=range(1, 8))
    p.set_defaults(func=cmd_list_context_combinations)

    p = subparsers.add_parser("validate-architectures", help="Run the full architecture connectivity/health check.")
    p.add_argument("--gateway-url", default="http://localhost:8000")
    p.add_argument("--skip-gateway", action="store_true")
    p.set_defaults(func=cmd_validate_architectures)

    subparsers.add_parser("validate-faults", help="Print the real fault catalog's verification tiers.").set_defaults(func=cmd_validate_faults)

    for name, func, default_metric in (
        ("analyze-necessity", cmd_analyze_necessity, "required_evidence_score"),
        ("analyze-composition", cmd_analyze_composition, "conclusion_correctness_score"),
    ):
        p = subparsers.add_parser(name, help=f"Run the {name.replace('-', ' ')} analysis for one use case.")
        p.add_argument("--use-case", required=True)
        p.add_argument("--suite", default="tep-v2")
        p.add_argument("--results-root", default="results")
        p.add_argument("--metric", default=default_metric)
        p.set_defaults(func=func)

    for name, func in (
        ("analyze-sufficiency", cmd_analyze_sufficiency),
        ("analyze-representation", cmd_analyze_representation),
        ("analyze-architecture", cmd_analyze_architecture),
    ):
        p = subparsers.add_parser(name, help=f"Run the {name.replace('-', ' ')} analysis for one use case.")
        p.add_argument("--use-case", required=True)
        p.add_argument("--suite", default="tep-v2")
        p.add_argument("--results-root", default="results")
        p.set_defaults(func=func)

    p = subparsers.add_parser("generate-profiles", help="Generate Context Design Profiles for every use case with available evidence.")
    p.add_argument("--suite", default="tep-v2")
    p.add_argument("--results-root", default="results")
    p.add_argument("--out", default=None, help="Write JSON here instead of stdout.")
    p.set_defaults(func=cmd_generate_profiles)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except KeyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
