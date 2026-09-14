"""
Generates real, grounded `BenchmarkTask` YAMLs (`configs/benchmark/tasks_v2/
{enterprise,site,work_center,area_extra}.yaml`) FROM the controlled
benchmark context layer (`icab.benchmark_context.data`) -- one per KPI
value, one per hierarchy/membership relationship, and a set of
cross-entity comparison questions computed from the SAME deterministic
values the layer itself was seeded with (`scripts/seed_benchmark_context.py`).

Every task uses `d1_reactor_pressure_reading` as its `scenario_id` --
a NEUTRAL anchor scenario (no fault, simplest real TEP process
condition) purely so `ExperimentRunner.run_task` has a real scenario to
prepare; these tasks' own ground truth concerns ONLY the separately-
seeded, scenario-INDEPENDENT benchmark context layer, never the TEP
process state itself.

Ground truth text is deliberately GENERIC (never embeds the exact
synthetic numeric value the agent must retrieve) for value-lookup
questions -- consistent with every other ICAB v1/v2 measurement-QA
task; comparison questions DO state which entity has the higher/lower
value in the (researcher-only) ground truth conclusion, computed here
from the real synthetic data, never guessed.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from icab.benchmark_context import data

#: Two neutral anchor scenarios (no fault, real TEP process conditions
#: -- see module docstring for why the anchor's own process state is
#: irrelevant to these tasks' ground truth): the historian-only one for
#: KPI-value/comparison tasks, the historian+knowledge_graph one for
#: hierarchy/membership/count tasks that need real relationship queries.
ANCHOR_SCENARIO_HISTORIAN = "d1_reactor_pressure_reading"
ANCHOR_SCENARIO_KG = "d2_reactor_context_combination"
OUT_DIR = Path("configs/benchmark/tasks_v2")


def _kpi_value_task(task_id: str, use_case_id: str, kv: "data.KpiValue", isa95_level: str) -> dict:
    return {
        "task_id": task_id,
        "scenario_id": ANCHOR_SCENARIO_HISTORIAN,
        "task_type": "qa",
        "difficulty": "D1",
        "isa95_level": isa95_level,
        "use_case_id": use_case_id,
        "objective": f"What is the current value of {kv.entity_name}'s {kv.kpi.label.lower()}?",
        "available_architectures": ["historian"],
        "required_context_dimensions": ["C5"],
        "required_evidence": [kv.measurement_id],
        "expected_entities": [kv.measurement_id],
        "expected_relationships": [],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": (
                f"{kv.entity_name}'s {kv.kpi.label.lower()} ({kv.measurement_id}) is a controlled "
                f"benchmark KPI, retrievable from the historian in {kv.kpi.unit}."
            ),
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": [],
            "expected_relationships": [],
            "expected_evidence": [kv.measurement_id],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "grounding_score"], "pass_threshold": 1.0},
        "provenance": f"icab.benchmark_context: controlled synthetic KPI (src/icab/benchmark_context/data.py, version {data.BENCHMARK_CONTEXT_VERSION})",
        "version": "1.0.0",
    }


def _membership_task(task_id: str, use_case_id: str, isa95_level: str, child_id: str, child_name: str, parent_id: str, parent_name: str) -> dict:
    return {
        "task_id": task_id,
        "scenario_id": ANCHOR_SCENARIO_KG,
        "task_type": "qa",
        "difficulty": "D1",
        "isa95_level": isa95_level,
        "use_case_id": use_case_id,
        "objective": f"Is {child_name} part of {parent_name}?",
        "available_architectures": ["knowledge_graph"],
        "required_context_dimensions": ["C2", "C3"],
        "required_evidence": [parent_id],
        "expected_entities": [child_id, parent_id],
        "expected_relationships": [[child_id, "PART_OF", parent_id]],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": f"Yes -- {child_name} ({child_id}) is part of {parent_name} ({parent_id}).",
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": [],
            "expected_relationships": [[child_id, "PART_OF", parent_id]],
            "expected_evidence": [parent_id],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "relationship_score"], "pass_threshold": 1.0},
        "provenance": f"icab.benchmark_context: controlled synthetic hierarchy (src/icab/benchmark_context/data.py, version {data.BENCHMARK_CONTEXT_VERSION})",
        "version": "1.0.0",
    }


def _comparison_task(task_id: str, use_case_id: str, isa95_level: str, a: "data.KpiValue", b: "data.KpiValue") -> dict:
    winner, loser = (a, b) if a.value >= b.value else (b, a)
    return {
        "task_id": task_id,
        "scenario_id": ANCHOR_SCENARIO_HISTORIAN,
        "task_type": "investigation",
        "difficulty": "D2",
        "isa95_level": isa95_level,
        "use_case_id": use_case_id,
        "objective": (
            f"Between {a.entity_name} and {b.entity_name}, which one has the higher {a.kpi.label.lower()}?"
        ),
        "available_architectures": ["historian"],
        "required_context_dimensions": ["C5"],
        "required_evidence": [a.measurement_id, b.measurement_id],
        "expected_entities": [a.measurement_id, b.measurement_id],
        "expected_relationships": [],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": (
                f"{winner.entity_name} has the higher {a.kpi.label.lower()} "
                f"({winner.value} {winner.kpi.unit} vs {loser.value} {loser.kpi.unit} for {loser.entity_name})."
            ),
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": [],
            "expected_relationships": [],
            "expected_evidence": [a.measurement_id, b.measurement_id],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "grounding_score"], "pass_threshold": 1.0},
        "provenance": f"icab.benchmark_context: controlled synthetic KPI comparison (src/icab/benchmark_context/data.py, version {data.BENCHMARK_CONTEXT_VERSION})",
        "version": "1.0.0",
    }


def _count_task(task_id: str, use_case_id: str, isa95_level: str, objective: str, parent_id: str, parent_name: str, children: list[tuple[str, str]]) -> dict:
    names = ", ".join(name for _cid, name in children)
    return {
        "task_id": task_id,
        "scenario_id": ANCHOR_SCENARIO_KG,
        "task_type": "investigation",
        "difficulty": "D2",
        "isa95_level": isa95_level,
        "use_case_id": use_case_id,
        "objective": objective,
        "available_architectures": ["knowledge_graph"],
        "required_context_dimensions": ["C2", "C3"],
        "required_evidence": [parent_id],
        "expected_entities": [cid for cid, _name in children] + [parent_id],
        "expected_relationships": [[cid, "PART_OF", parent_id] for cid, _name in children],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": f"{parent_name} ({parent_id}) has {len(children)} such member(s): {names}.",
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": [],
            "expected_relationships": [[cid, "PART_OF", parent_id] for cid, _name in children],
            "expected_evidence": [parent_id],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "relationship_score", "completeness_score"], "pass_threshold": 1.0},
        "provenance": f"icab.benchmark_context: controlled synthetic hierarchy enumeration (src/icab/benchmark_context/data.py, version {data.BENCHMARK_CONTEXT_VERSION})",
        "version": "1.0.0",
    }


def _pairs(entities: list, count: int) -> list[tuple]:
    """Round-robin distinct unordered pairs from `entities`, `count` of them (wrapping if needed)."""

    from itertools import combinations

    all_pairs = list(combinations(entities, 2))
    if not all_pairs:
        return []
    return [all_pairs[i % len(all_pairs)] for i in range(count)]


def build_enterprise_tasks() -> list[dict]:
    tasks = []
    kpi_values = data.enterprise_kpi_values()
    for kv in kpi_values:
        tasks.append(_kpi_value_task(f"ent-qa-{kv.kpi.key}", "enterprise-kpi-interpretation", kv, "enterprise"))

    for site in data.SITES:
        tasks.append(_membership_task(
            f"ent-qa-{site.key}-site-membership", "enterprise-site-portfolio", "enterprise",
            site.canonical_id, site.name, data.ENTERPRISE_ID, data.ENTERPRISE_NAME,
        ))

    tasks.append(_count_task(
        "ent-investigation-site-count", "enterprise-site-portfolio", "enterprise",
        "How many sites belong to the Northwind Chemical enterprise, and which ones?",
        data.ENTERPRISE_ID, data.ENTERPRISE_NAME,
        [(s.canonical_id, s.name) for s in data.SITES],
    ))

    # Cross-site KPI comparisons -- genuinely enterprise-level (portfolio) reasoning.
    site_kpi_values = data.site_kpi_values()
    by_kpi: dict[str, list] = {}
    for kv in site_kpi_values:
        by_kpi.setdefault(kv.kpi.key, []).append(kv)

    comparisons_needed = 50 - len(tasks)
    kpi_keys = list(by_kpi.keys())
    idx = 0
    while comparisons_needed > 0 and kpi_keys:
        kpi_key = kpi_keys[idx % len(kpi_keys)]
        values = by_kpi[kpi_key]
        pair = _pairs(values, 1)[0]
        tasks.append(_comparison_task(
            f"ent-investigation-compare-{kpi_key}-{idx}", "enterprise-site-portfolio", "enterprise", pair[0], pair[1],
        ))
        comparisons_needed -= 1
        idx += 1

    return tasks[:50]


def build_site_tasks() -> list[dict]:
    tasks = []
    kpi_values = data.site_kpi_values()
    for kv in kpi_values:
        tasks.append(_kpi_value_task(f"site-qa-{kv.entity_id.split(':')[-1]}-{kv.kpi.key}", "site-kpi-interpretation", kv, "site"))

    for area in data.AREAS:
        site = data.site_by_key(area.site_key)
        tasks.append(_membership_task(
            f"site-qa-{area.key}-area-membership", "site-area-portfolio", "site",
            area.canonical_id, area.name, site.canonical_id, site.name,
        ))
        if len(tasks) >= 50:
            break

    remaining = 50 - len(tasks)
    if remaining > 0:
        by_kpi: dict[str, list] = {}
        for kv in kpi_values:
            by_kpi.setdefault(kv.kpi.key, []).append(kv)
        kpi_keys = list(by_kpi.keys())
        idx = 0
        while remaining > 0 and kpi_keys:
            kpi_key = kpi_keys[idx % len(kpi_keys)]
            values = by_kpi[kpi_key]
            pairs = _pairs(values, 1)
            if pairs:
                a, b = pairs[0]
                tasks.append(_comparison_task(f"site-investigation-compare-{kpi_key}-{idx}", "site-cross-comparison", "site", a, b))
                remaining -= 1
            idx += 1
            if idx > 200:
                break

    return tasks[:50]


def build_work_center_tasks() -> list[dict]:
    tasks = []
    kpi_values = data.work_center_kpi_values()
    for kv in kpi_values:
        tasks.append(_kpi_value_task(f"wc-qa-{kv.entity_id.split(':')[-1]}-{kv.kpi.key}", "work-center-kpi-interpretation", kv, "work_center"))

    for wc in data.WORK_CENTERS:
        area = data.area_by_key(wc.area_key)
        tasks.append(_membership_task(
            f"wc-qa-{wc.key}-area-membership", "work-center-area-membership", "work_center",
            wc.canonical_id, wc.name, area.canonical_id, area.name,
        ))

    remaining = 50 - len(tasks)
    if remaining > 0:
        by_kpi: dict[str, list] = {}
        for kv in kpi_values:
            by_kpi.setdefault(kv.kpi.key, []).append(kv)
        kpi_keys = list(by_kpi.keys())
        idx = 0
        while remaining > 0 and kpi_keys:
            kpi_key = kpi_keys[idx % len(kpi_keys)]
            values = by_kpi[kpi_key]
            pairs = _pairs(values, 1)
            if pairs:
                a, b = pairs[0]
                tasks.append(_comparison_task(f"wc-investigation-compare-{kpi_key}-{idx}", "work-center-cross-comparison", "work_center", a, b))
                remaining -= 1
            idx += 1
            if idx > 200:
                break

    return tasks[:50]


def build_area_extra_tasks(existing_count: int) -> list[dict]:
    """Extra, real, grounded Area-level questions using the (now enriched) controlled area layer -- fills toward 50 alongside the 3 real, hand-authored tep-v2 Area tasks."""

    tasks = []
    kpi_values = data.area_kpi_values()
    for kv in kpi_values:
        tasks.append(_kpi_value_task(f"area-ctx-qa-{kv.entity_id.split(':')[-1]}-{kv.kpi.key}", "area-kpi-interpretation", kv, "area"))

    for area in data.AREAS:
        site = data.site_by_key(area.site_key)
        tasks.append(_membership_task(
            f"area-ctx-qa-{area.key}-site-membership", "area-site-membership-identification", "area",
            area.canonical_id, area.name, site.canonical_id, site.name,
        ))

    for wc in data.WORK_CENTERS:
        area = data.area_by_key(wc.area_key)
        tasks.append(_membership_task(
            f"area-ctx-qa-{wc.key}-membership", "area-work-center-composition", "area",
            wc.canonical_id, wc.name, area.canonical_id, area.name,
        ))

    remaining = 50 - existing_count - len(tasks)
    if remaining > 0:
        by_kpi: dict[str, list] = {}
        for kv in kpi_values:
            by_kpi.setdefault(kv.kpi.key, []).append(kv)
        kpi_keys = list(by_kpi.keys())
        idx = 0
        while remaining > 0 and kpi_keys:
            kpi_key = kpi_keys[idx % len(kpi_keys)]
            values = by_kpi[kpi_key]
            pairs = _pairs(values, 1)
            if pairs:
                a, b = pairs[0]
                tasks.append(_comparison_task(f"area-ctx-investigation-compare-{kpi_key}-{idx}", "area-cross-comparison", "area", a, b))
                remaining -= 1
            idx += 1
            if idx > 200:
                break

    return tasks[: max(0, 50 - existing_count)]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    enterprise_tasks = build_enterprise_tasks()
    (OUT_DIR / "enterprise.yaml").write_text(yaml.safe_dump({"tasks": enterprise_tasks}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"enterprise: wrote {len(enterprise_tasks)} task(s)")

    site_tasks = build_site_tasks()
    (OUT_DIR / "site.yaml").write_text(yaml.safe_dump({"tasks": site_tasks}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"site: wrote {len(site_tasks)} task(s)")

    wc_tasks = build_work_center_tasks()
    (OUT_DIR / "work_center.yaml").write_text(yaml.safe_dump({"tasks": wc_tasks}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"work_center: wrote {len(wc_tasks)} task(s)")

    # Area already has 3 real, hand-authored tep-v2 tasks -- top up toward 50.
    area_tasks = build_area_extra_tasks(existing_count=3)
    (OUT_DIR / "area_context.yaml").write_text(yaml.safe_dump({"tasks": area_tasks}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"area (extra, controlled-context): wrote {len(area_tasks)} task(s) (+3 existing real tep-v2 tasks = {len(area_tasks) + 3})")


if __name__ == "__main__":
    main()
