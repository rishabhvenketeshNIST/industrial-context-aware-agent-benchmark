"""
ICAB v2: generates `configs/benchmark/tasks_v2/*.yaml` from the REAL,
already-registered tep-v1 task suite (`configs/benchmark/tasks/`) by
adding `isa95_level`/`use_case_id` to each task -- it does NOT invent,
rewrite, or re-derive any task content (objective, ground_truth,
required_evidence, evaluation_criteria all copied byte-for-byte). This
keeps tep-v1 completely untouched while giving tep-v2 the ISA-95/
use-case classification metadata it needs, without duplicating or
re-authoring 38 tasks' worth of already-validated content by hand.

The task_id -> use_case_id assignment below is a literal, reviewable
mapping table (not a fuzzy heuristic) -- every one of the 38 real tep-v1
task ids is listed explicitly; the script fails loudly if the real
inventory and this table ever drift apart (a task added to tep-v1
without updating this table, or vice versa).

Run:

    uv run python scripts/generate_tep_v2_tasks.py

Regenerates configs/benchmark/tasks_v2/*.yaml deterministically -- safe
to re-run any time tep-v1's task content changes (the classification
stays the same; only the copied content updates).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

SCENARIOS_DIR = Path("configs/benchmark/scenarios")
TASKS_V1_DIR = Path("configs/benchmark/tasks")
USECASES_DIR = Path("configs/usecases")
TASKS_V2_DIR = Path("configs/benchmark/tasks_v2")

#: Explicit task_id -> use_case_id assignment for every real tep-v1 task.
#: Grouped by use case for reviewability; see configs/usecases/*.yaml for
#: what each use case means and configs/benchmark/specification-v2.md
#: for the classification rationale (task_type/required_context match,
#: equipment-anchored vs. plant-wide framing).
TASK_TO_USE_CASE: dict[str, str] = {
    # -- eq-current-value-interpretation --
    "d1-qa-current-level": "eq-current-value-interpretation",
    "d1-qa-current-pressure": "eq-current-value-interpretation",
    "d1-qa-current-temperature": "eq-current-value-interpretation",
    "d1-investigation-pressure-and-temperature": "eq-current-value-interpretation",
    "d2cooling-qa-current-value": "eq-current-value-interpretation",
    "d4feed-qa-feed-system-check": "eq-current-value-interpretation",
    "d4unknown-qa-separator-or-stripper": "eq-current-value-interpretation",
    # -- eq-value-and-relationship-combination --
    "d2cooling-investigation-value-and-equipment": "eq-value-and-relationship-combination",
    "d2cooling-investigation-isolated-or-broader": "eq-value-and-relationship-combination",
    "d2ctx-investigation-combine-value-and-relationship": "eq-value-and-relationship-combination",
    "d2ctx-investigation-pressure-level-and-relationship": "eq-value-and-relationship-combination",
    "d2ctx-qa-level-equipment": "eq-value-and-relationship-combination",
    "d2ctx-qa-monitors-relationship-confirmed": "eq-value-and-relationship-combination",
    # -- eq-control-relationship-identification --
    "d2ctx-qa-cooling-valve-controls-temperature": "eq-control-relationship-identification",
    # -- eq-temporal-trend-interpretation --
    "d1-qa-pressure-stability": "eq-temporal-trend-interpretation",
    "d1-investigation-pressure-trend": "eq-temporal-trend-interpretation",
    "d3pressure-qa-trend-direction": "eq-temporal-trend-interpretation",
    "d3stream4-qa-compressor-trend": "eq-temporal-trend-interpretation",
    # -- eq-historical-pattern-characterization --
    "d3stochastic-qa-gradual-or-instantaneous": "eq-historical-pattern-characterization",
    "d3stochastic-investigation-full-window-characterization": "eq-historical-pattern-characterization",
    # -- eq-abnormal-behavior-diagnosis --
    "d2cooling-diagnosis-heat-transfer-category": "eq-abnormal-behavior-diagnosis",
    "d3pressure-diagnosis-disturbance-category": "eq-abnormal-behavior-diagnosis",
    "d3pressure-diagnosis-trend-and-equipment": "eq-abnormal-behavior-diagnosis",
    "d3stochastic-diagnosis-gradual-trend": "eq-abnormal-behavior-diagnosis",
    "d3stochastic-diagnosis-step-vs-drift": "eq-abnormal-behavior-diagnosis",
    "d3stream4-diagnosis-drift-and-equipment": "eq-abnormal-behavior-diagnosis",
    "d4feed-diagnosis-explain-naming-mismatch": "eq-abnormal-behavior-diagnosis",
    "d4feed-diagnosis-investigate-suspected-feed-system": "eq-abnormal-behavior-diagnosis",
    # -- eq-related-measurement-discovery --
    "d3pressure-investigation-related-measurements": "eq-related-measurement-discovery",
    "d3stream4-investigation-implicated-equipment": "eq-related-measurement-discovery",
    "d4feed-investigation-actual-affected-equipment": "eq-related-measurement-discovery",
    # -- pc-equipment-composition-discovery --
    "d4plant-qa-discover-equipment": "pc-equipment-composition-discovery",
    # -- pc-open-ended-abnormal-investigation --
    "d4plant-investigation-open-ended": "pc-open-ended-abnormal-investigation",
    "d4unknown-investigation-open-ended": "pc-open-ended-abnormal-investigation",
    # -- pc-selective-evidence-retrieval --
    "d4plant-investigation-selective-retrieval": "pc-selective-evidence-retrieval",
    # -- pc-cross-unit-diagnosis --
    "d4plant-diagnosis-reactor-vs-downstream": "pc-cross-unit-diagnosis",
    "d4unknown-diagnosis-implicated-equipment": "pc-cross-unit-diagnosis",
    # -- pc-relational-structure-enumeration --
    "d4unknown-investigation-relationship-enumeration": "pc-relational-structure-enumeration",
}


def main() -> int:
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V1_DIR, scenario_registry=scenario_registry)
    use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)

    real_task_ids = set(task_registry.list_ids())
    mapped_task_ids = set(TASK_TO_USE_CASE)

    missing = real_task_ids - mapped_task_ids
    stale = mapped_task_ids - real_task_ids
    if missing or stale:
        print("error: TASK_TO_USE_CASE has drifted from the real tep-v1 task inventory:", file=sys.stderr)
        if missing:
            print(f"  tasks in tep-v1 but NOT in TASK_TO_USE_CASE: {sorted(missing)}", file=sys.stderr)
        if stale:
            print(f"  ids in TASK_TO_USE_CASE that no longer exist in tep-v1: {sorted(stale)}", file=sys.stderr)
        return 1

    TASKS_V2_DIR.mkdir(parents=True, exist_ok=True)

    # Group tep-v1 task YAML files by their own scenario id's source
    # file's own grouping (one output file per source tep-v1 file, same
    # basenames) -- preserves the same "several tasks per file" layout
    # tep-v1 uses, so a v2 task file is easy to compare against its v1
    # counterpart directly.
    written: list[Path] = []
    for source_path in sorted(TASKS_V1_DIR.glob("*.yaml")):
        with source_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        entries = data.get("tasks", [])
        if not entries:
            continue

        augmented_entries = []
        for entry in entries:
            task_id = entry["task_id"]
            use_case_id = TASK_TO_USE_CASE[task_id]
            use_case = use_case_registry.get(use_case_id)

            augmented = dict(entry)
            augmented["isa95_level"] = use_case.isa95_level.value
            augmented["use_case_id"] = use_case_id
            augmented_entries.append(augmented)

        output_path = TASKS_V2_DIR / source_path.name
        with output_path.open("w", encoding="utf-8") as file:
            file.write(
                f"# GENERATED by scripts/generate_tep_v2_tasks.py from {source_path} --\n"
                "# do not hand-edit; re-run the generator instead. Task content\n"
                "# (objective/ground_truth/required_evidence/evaluation_criteria) is\n"
                "# copied byte-for-byte from the real tep-v1 task; only isa95_level/\n"
                "# use_case_id are added.\n\n"
            )
            yaml.safe_dump({"tasks": augmented_entries}, file, sort_keys=False, allow_unicode=True)

        written.append(output_path)

    print(f"Wrote {len(written)} file(s) under {TASKS_V2_DIR}/:")
    for path in written:
        print(f"  {path}")
    print(f"Classified {len(mapped_task_ids)} tasks across {len(set(TASK_TO_USE_CASE.values()))} use cases.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
