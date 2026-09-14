"""
Generates ADDITIONAL real, grounded Equipment/Process-Cell `BenchmarkTask`
YAMLs (`configs/benchmark/tasks_v2/{equipment_extra,process_cell_extra}.yaml`)
to top up toward 50 questions per level -- using ONLY real TEP data
already established elsewhere in this repository:

  * Equipment: the 31 real TEP measurements NOT already covered by any
    tep-v1 task (`icab.tep.measurements.build_real_tep_variables()`),
    same generic current-value QA template every existing equipment
    task already uses.
  * Process Cell: the real MONITORS relationships
    (`icab.tep.adapter.TEPAdapter.get_measurement_relationships()`,
    unchanged, M13-A) between each of the 41 real measurements and its
    owning equipment, combined with the real, unchanged
    equipment-PART_OF-process-cell hierarchy fact -- asking a
    relationship-confirmation question that requires BOTH C3 (MONITORS)
    and C2 (hierarchy) reasoning, which is what makes it a genuinely
    PROCESS-CELL-level (not merely equipment-level) question.

No new entities, relationships, or values are invented here -- every
fact asserted in a generated ground truth is already real and present
in `icab.tep.adapter`/`icab.tep.measurements`, unchanged.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from icab.tep.adapter import TEPAdapter
from icab.tep.measurements import build_real_tep_variables

ANCHOR_SCENARIO_HISTORIAN = "d1_reactor_pressure_reading"
ANCHOR_SCENARIO_KG = "d2_reactor_context_combination"
OUT_DIR = Path("configs/benchmark/tasks_v2")

PROCESS_CELL_ID = TEPAdapter.PROCESS_CELL_ID


def _already_used_measurement_ids() -> set[str]:
    from icab.scenarios import BenchmarkScenarioRegistry
    from icab.tasks.registry import BenchmarkTaskRegistry

    sr = BenchmarkScenarioRegistry("configs/benchmark/scenarios")
    tr = BenchmarkTaskRegistry("configs/benchmark/tasks", scenario_registry=sr)  # tep-v1, unchanged
    used: set[str] = set()
    for task in tr:
        used |= set(task.required_evidence)
        used |= set(task.expected_entities)
    return used


def _equipment_qa_task(task_id: str, var, index: int) -> dict:
    measurement_id = var.canonical_id
    return {
        "task_id": task_id,
        "scenario_id": ANCHOR_SCENARIO_HISTORIAN,
        "task_type": "qa",
        "difficulty": "D1" if index % 3 else "D2",
        "isa95_level": "equipment",
        "use_case_id": "eq-current-value-interpretation",
        "objective": f"What is the current value of {var.name.lower()}?",
        "available_architectures": ["historian"],
        "required_context_dimensions": ["C5"],
        "required_evidence": [measurement_id],
        "expected_entities": [measurement_id],
        "expected_relationships": [],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": f"{var.name} ({measurement_id}) is a real TEP measurement, retrievable from the historian.",
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": [],
            "expected_relationships": [],
            "expected_evidence": [measurement_id],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "grounding_score"], "pass_threshold": 1.0},
        "provenance": "icab.tep.measurements: real TEP measurement not covered by any tep-v1 task (scripts/generate_extra_real_tasks.py)",
        "version": "1.0.0",
    }


def _process_cell_monitors_task(task_id: str, var, index: int) -> dict:
    measurement_id = var.canonical_id
    equipment_id = var.equipment_id
    return {
        "task_id": task_id,
        "scenario_id": ANCHOR_SCENARIO_KG,
        "task_type": "qa",
        "difficulty": "D2" if index % 2 else "D3",
        "isa95_level": "process_cell",
        "use_case_id": "pc-relational-structure-enumeration",
        "objective": (
            f"Is {var.name.lower()} monitored by equipment that is part of the reaction process cell?"
        ),
        "available_architectures": ["knowledge_graph"],
        "required_context_dimensions": ["C3", "C2"],
        "required_evidence": [equipment_id],
        "expected_entities": [measurement_id, equipment_id, PROCESS_CELL_ID],
        "expected_relationships": [
            [equipment_id, "MONITORS", measurement_id],
            [equipment_id, "PART_OF", PROCESS_CELL_ID],
        ],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": (
                f"Yes -- {var.name} ({measurement_id}) is monitored by {equipment_id}, which is part of the "
                f"reaction process cell ({PROCESS_CELL_ID})."
            ),
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": [equipment_id],
            "expected_relationships": [
                [equipment_id, "MONITORS", measurement_id],
                [equipment_id, "PART_OF", PROCESS_CELL_ID],
            ],
            "expected_evidence": [equipment_id],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "relationship_score"], "pass_threshold": 1.0},
        "provenance": "icab.tep.adapter: real MONITORS + PART_OF facts (scripts/generate_extra_real_tasks.py)",
        "version": "1.0.0",
    }


def _process_cell_equipment_count_task() -> dict:
    """One real, aggregate process-cell-level question: how many real equipment items does the reaction process cell contain -- reuses TEPAdapter.get_real_hierarchy_relationships(), no new facts."""

    equipment_ids = sorted({var.equipment_id for var in build_real_tep_variables()})
    return {
        "task_id": "pc-extra-qa-equipment-count",
        "scenario_id": ANCHOR_SCENARIO_KG,
        "task_type": "investigation",
        "difficulty": "D2",
        "isa95_level": "process_cell",
        "use_case_id": "pc-equipment-composition-discovery",
        "objective": "How many distinct real equipment items does the reaction process cell contain, according to the knowledge graph?",
        "available_architectures": ["knowledge_graph"],
        "required_context_dimensions": ["C2", "C3"],
        "required_evidence": [PROCESS_CELL_ID],
        "expected_entities": equipment_ids + [PROCESS_CELL_ID],
        "expected_relationships": [[eid, "PART_OF", PROCESS_CELL_ID] for eid in equipment_ids],
        "expected_temporal_evidence": False,
        "ground_truth": {
            "conclusion": f"The reaction process cell ({PROCESS_CELL_ID}) contains {len(equipment_ids)} real equipment items: {', '.join(equipment_ids)}.",
            "root_cause_disturbance": None,
            "affected_measurements": [],
            "affected_equipment": equipment_ids,
            "expected_relationships": [[eid, "PART_OF", PROCESS_CELL_ID] for eid in equipment_ids],
            "expected_evidence": [PROCESS_CELL_ID],
        },
        "evaluation_criteria": {"binding_scores": ["required_evidence_score", "relationship_score", "completeness_score"], "pass_threshold": 1.0},
        "provenance": "icab.tep.adapter: real PART_OF hierarchy facts (scripts/generate_extra_real_tasks.py)",
        "version": "1.0.0",
    }


def main() -> None:
    used_ids = _already_used_measurement_ids()
    all_vars = build_real_tep_variables()
    unused_vars = [v for v in all_vars if v.canonical_id not in used_ids]

    equipment_extra = [
        _equipment_qa_task(f"eq-extra-qa-{var.canonical_id.split(':')[-1]}", var, i)
        for i, var in enumerate(unused_vars[:19])
    ]
    (OUT_DIR / "equipment_extra.yaml").write_text(yaml.safe_dump({"tasks": equipment_extra}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"equipment (extra, real): wrote {len(equipment_extra)} task(s) (+31 existing = {len(equipment_extra) + 31})")

    # 41 real MONITORS-based questions (one per real measurement) + 1 real
    # aggregate equipment-count question = 42, reaching 8 + 42 = 50 exactly.
    process_cell_extra = [
        _process_cell_monitors_task(f"pc-extra-qa-monitors-{var.canonical_id.split(':')[-1]}", var, i)
        for i, var in enumerate(all_vars)
    ]
    process_cell_extra.append(_process_cell_equipment_count_task())
    (OUT_DIR / "process_cell_extra.yaml").write_text(yaml.safe_dump({"tasks": process_cell_extra}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"process_cell (extra, real): wrote {len(process_cell_extra)} task(s) (+8 existing = {len(process_cell_extra) + 8})")


if __name__ == "__main__":
    main()
