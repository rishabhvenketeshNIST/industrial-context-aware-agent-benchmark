"""
Generates `IndustrialUseCase` YAMLs for the new Enterprise/Site/Work-Center
use cases (`configs/usecases/{enterprise,site,work_center}.yaml`) and the
new Area use cases appended to the existing `configs/usecases/area.yaml`
-- derived DIRECTLY from the real, already-generated
`configs/benchmark/tasks_v2/*.yaml` task content (never hand-typed
separately), so a use case's `required_context`/`candidate_context`/
`applicable_scenarios` always agree with what its own tasks actually
declare.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import yaml

TASKS_DIR = Path("configs/benchmark/tasks_v2")
USECASES_DIR = Path("configs/usecases")

#: use_case_id -> (name, description, difficulty) -- the only genuinely
#: new (not task-derived) authoring per use case; everything else is
#: computed from its tasks below.
NEW_USE_CASE_META: dict[str, tuple[str, str, str]] = {
    "enterprise-kpi-interpretation": (
        "Interpret enterprise-level KPIs",
        "Retrieve and interpret a controlled-benchmark enterprise-level KPI (production/revenue/safety/energy/quality target) for Northwind Chemical.",
        "D1",
    ),
    "enterprise-site-portfolio": (
        "Reason about the enterprise's site portfolio",
        "Determine which sites belong to the enterprise, and compare site-level performance across the enterprise's real+controlled-benchmark site portfolio.",
        "D2",
    ),
    "site-kpi-interpretation": (
        "Interpret site-level KPIs",
        "Retrieve and interpret a controlled-benchmark site-level KPI (production, headcount, safety, energy, utilization, ...).",
        "D1",
    ),
    "site-area-portfolio": (
        "Reason about a site's area composition",
        "Determine which areas belong to a given site.",
        "D1",
    ),
    "site-cross-comparison": (
        "Compare KPIs across sites",
        "Compare a specific KPI across two sites to determine which one performs better on it.",
        "D2",
    ),
    "work-center-kpi-interpretation": (
        "Interpret work-center-level KPIs",
        "Retrieve and interpret a controlled-benchmark work-center-level KPI (resources, scheduling, utilization, throughput, ...).",
        "D1",
    ),
    "work-center-area-membership": (
        "Confirm work-center-to-area membership",
        "Confirm which area a given work center belongs to.",
        "D1",
    ),
    "work-center-cross-comparison": (
        "Compare KPIs across work centers",
        "Compare a specific KPI across two work centers to determine which one performs better on it.",
        "D2",
    ),
    "area-kpi-interpretation": (
        "Interpret area-level KPIs",
        "Retrieve and interpret a controlled-benchmark area-level KPI (production rate, utilization, work orders, safety, ...).",
        "D1",
    ),
    "area-work-center-composition": (
        "Discover an area's work-center composition",
        "Determine which work centers belong to a given area.",
        "D1",
    ),
    "area-cross-comparison": (
        "Compare KPIs across areas",
        "Compare a specific KPI across two areas to determine which one performs better on it.",
        "D2",
    ),
}


def _load_tasks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("tasks", [])


def build_use_cases_for_level(level: str, task_files: list[str]) -> list[dict]:
    tasks_by_use_case: dict[str, list[dict]] = defaultdict(list)
    for filename in task_files:
        for task in _load_tasks(TASKS_DIR / filename):
            if task.get("use_case_id") in NEW_USE_CASE_META:
                tasks_by_use_case[task["use_case_id"]].append(task)

    use_cases = []
    for use_case_id, tasks in tasks_by_use_case.items():
        name, description, difficulty = NEW_USE_CASE_META[use_case_id]

        required = sorted({dim for t in tasks for dim in t["required_context_dimensions"]})
        scenarios = sorted({t["scenario_id"] for t in tasks})
        task_type_counts = Counter(t["task_type"] for t in tasks)
        predominant_task_type = task_type_counts.most_common(1)[0][0]

        binding_scores = sorted({score for t in tasks for score in t["evaluation_criteria"]["binding_scores"]})

        use_cases.append({
            "use_case_id": use_case_id,
            "name": name,
            "description": description,
            "isa95_level": level,
            "task_type": predominant_task_type,
            "required_context": required,
            "candidate_context": required,
            "success_criteria": {"binding_scores": binding_scores, "pass_threshold": 1.0},
            "applicable_scenarios": scenarios,
            "difficulty": difficulty,
            "provenance": "icab.benchmark_context: controlled benchmark KPI/hierarchy use case (scripts/generate_synthetic_level_usecases.py)",
            "version": "1.0.0",
        })

    return sorted(use_cases, key=lambda uc: uc["use_case_id"])


def main() -> None:
    enterprise_ucs = build_use_cases_for_level("enterprise", ["enterprise.yaml"])
    (USECASES_DIR / "enterprise.yaml").write_text(yaml.safe_dump({"use_cases": enterprise_ucs}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"enterprise: {len(enterprise_ucs)} use case(s)")

    site_ucs = build_use_cases_for_level("site", ["site.yaml"])
    (USECASES_DIR / "site.yaml").write_text(yaml.safe_dump({"use_cases": site_ucs}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"site: {len(site_ucs)} use case(s)")

    wc_ucs = build_use_cases_for_level("work_center", ["work_center.yaml"])
    (USECASES_DIR / "work_center.yaml").write_text(yaml.safe_dump({"use_cases": wc_ucs}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"work_center: {len(wc_ucs)} use case(s)")

    # Area: APPEND the new use cases to the existing, real, hand-authored area.yaml (never overwrite the existing 2).
    new_area_ucs = build_use_cases_for_level("area", ["area_context.yaml"])
    existing_area_path = USECASES_DIR / "area.yaml"
    existing_area_data = yaml.safe_load(existing_area_path.read_text(encoding="utf-8")) or {}
    existing_area_ucs = existing_area_data.get("use_cases", [])
    combined = existing_area_ucs + new_area_ucs
    existing_area_path.write_text(yaml.safe_dump({"use_cases": combined}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"area: {len(existing_area_ucs)} existing + {len(new_area_ucs)} new = {len(combined)} use case(s)")


if __name__ == "__main__":
    main()
