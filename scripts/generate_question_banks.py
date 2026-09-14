"""
Generates the Equipment/Process-Cell/Area question banks
(`configs/questions/<level>/generated.yaml`) FROM the real, already-
validated tep-v2 `BenchmarkTask` inventory -- one `Question` per task,
reusing that task's own real objective/ground-truth/context-dimension
declarations as-is (never re-authored, never re-verified content, just
reorganized under the new `icab.questions.Question` schema).

`difficulty`/`difficulty_factors`/`expected_answer_type`/`tags` are
derived by a SMALL, DETERMINISTIC, DOCUMENTED heuristic over each task's
own already-real fields (below) -- not independently hand-verified per
question given the volume (40 tasks). This is stated explicitly, here
and in `docs/benchmark/specification-v3.md`, rather than presented as a
per-question expert judgment.

Genuinely NEW Process-Cell/Area questions (beyond what tep-v2 already
has) are hand-authored SEPARATELY in `configs/questions/process_cell/new.yaml`
/ `configs/questions/area/new.yaml` -- this script only regenerates the
REUSED portion, and never overwrites those hand-authored files.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from icab.questions.models import DifficultyFactors, ExpectedAnswerType, QuestionDifficulty
from icab.questions.taxonomy import QuestionCategory
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.context_dimensions import ContextDimension
from icab.tasks.registry import BenchmarkTaskRegistry

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
OUT_DIR = Path("configs/questions")

_DIMENSION_TAGS: dict[ContextDimension, QuestionCategory] = {
    ContextDimension.C1_SEMANTIC: QuestionCategory.IDENTIFICATION,
    ContextDimension.C2_ASSET_HIERARCHY: QuestionCategory.RELATIONSHIP_REASONING,
    ContextDimension.C3_RELATIONAL: QuestionCategory.RELATIONSHIP_REASONING,
    ContextDimension.C4_TEMPORAL: QuestionCategory.TEMPORAL_REASONING,
    ContextDimension.C5_OPERATIONAL: QuestionCategory.MEASUREMENT_INTERPRETATION,
    ContextDimension.C6_PROCEDURAL: QuestionCategory.PROCEDURAL_REASONING,
    ContextDimension.C7_HISTORICAL: QuestionCategory.HISTORICAL_REASONING,
}

_TASK_TYPE_ANSWER: dict[str, ExpectedAnswerType] = {
    "qa": ExpectedAnswerType.NUMERIC_VALUE,
    "investigation": ExpectedAnswerType.FREE_TEXT_EXPLANATION,
    "diagnosis": ExpectedAnswerType.ROOT_CAUSE_CATEGORY,
}

_TASK_TYPE_TAG: dict[str, QuestionCategory] = {
    "qa": QuestionCategory.CONTEXTUALIZED_QA,
    "diagnosis": QuestionCategory.DIAGNOSIS,
}


def _difficulty_factors(task) -> DifficultyFactors:
    dims = task.required_context_dimensions
    return DifficultyFactors(
        n_sources=len(task.available_architectures),
        relationship_depth=1 if (ContextDimension.C3_RELATIONAL in dims or ContextDimension.C6_PROCEDURAL in dims) else 0,
        requires_temporal_reasoning=ContextDimension.C4_TEMPORAL in dims or ContextDimension.C7_HISTORICAL in dims,
        requires_cross_source_reasoning=len(task.available_architectures) > 1,
        evidence_requirement_count=max(len(task.required_evidence), 1),
    )


def _difficulty(factors: DifficultyFactors) -> QuestionDifficulty:
    score = sum(
        [
            factors.n_sources > 1,
            factors.relationship_depth > 0,
            factors.requires_temporal_reasoning,
            factors.requires_cross_source_reasoning,
            factors.evidence_requirement_count > 1,
        ]
    )
    if score <= 1:
        return QuestionDifficulty.BASIC
    if score <= 3:
        return QuestionDifficulty.INTERMEDIATE
    return QuestionDifficulty.ADVANCED


def _expected_answer_type(task) -> ExpectedAnswerType:
    if task.task_type.value == "qa" and ContextDimension.C3_RELATIONAL in task.required_context_dimensions:
        return ExpectedAnswerType.RELATIONSHIP_CONFIRMATION
    return _TASK_TYPE_ANSWER[task.task_type.value]


def _tags(task) -> list[str]:
    tags = {_DIMENSION_TAGS[d] for d in task.required_context_dimensions}
    if task.task_type.value in _TASK_TYPE_TAG:
        tags.add(_TASK_TYPE_TAG[task.task_type.value])
    if len(task.available_architectures) > 1:
        tags.add(QuestionCategory.CROSS_SOURCE_REASONING)
    if task.required_evidence:
        tags.add(QuestionCategory.EVIDENCE_VERIFICATION)
    return sorted(t.value for t in tags)


def build_questions_for_level(task_registry: BenchmarkTaskRegistry, level: str) -> list[dict]:
    questions = []
    for task in sorted(task_registry, key=lambda t: t.task_id):
        if task.isa95_level is None or task.isa95_level.value != level:
            continue

        factors = _difficulty_factors(task)
        question = {
            "question_id": f"Q-{task.task_id}",
            "benchmark_id": f"icab-{level.replace('_', '-')}-v1",
            "use_case_id": task.use_case_id,
            "isa95_level": level,
            "question_text": task.objective,
            "task_type": task.task_type.value,
            "objective": task.objective,
            "hypothesized_required_context": [d.value for d in task.required_context_dimensions],
            "expected_evidence_description": (
                f"Evidence matching required_evidence {task.required_evidence!r}" if task.required_evidence
                else "Evidence sufficient to support the ground-truth conclusion."
            ),
            "expected_answer_type": _expected_answer_type(task).value,
            "compatible_scenarios": [task.scenario_id],
            "realizations": {task.scenario_id: task.task_id},
            "difficulty": _difficulty(factors).value,
            "difficulty_factors": factors.model_dump(),
            "tags": _tags(task),
            "version": "1.0.0",
            "validation_status": "validated",
            "provenance": f"generated from tep-v2 task {task.task_id!r} (scripts/generate_question_banks.py)",
        }
        questions.append(question)
    return questions


def main() -> None:
    scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)

    for level in ("equipment", "process_cell", "area", "enterprise", "site", "work_center"):
        questions = build_questions_for_level(task_registry, level)
        out_path = OUT_DIR / level / "generated.yaml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as file:
            yaml.safe_dump({"questions": questions}, file, sort_keys=False, allow_unicode=True)
        print(f"{level}: wrote {len(questions)} question(s) -> {out_path}")


if __name__ == "__main__":
    main()
