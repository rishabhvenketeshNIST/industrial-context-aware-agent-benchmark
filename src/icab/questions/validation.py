"""
Formal, reportable question-bank validation (ICAB v3 50-question
milestone, Section 25) -- makes EXPLICIT and REPORTABLE what
`QuestionBankRegistry`'s own construction-time checks already enforce
(duplicate ids, unknown use case/scenario/task references, isa95_level
agreement), plus a few additional checks that are true validations, not
merely re-statements of what already can't fail once a registry
constructs successfully. Only questions that pass EVERY check are
`VALIDATED` and eligible for `icab.benchmark.question_runner
.QuestionBenchmarkRunner` -- see `icab.questions.models.ValidationStatus`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.tasks.benchmark_task import KNOWN_SCORE_FIELDS
from icab.tasks.registry import BenchmarkTaskRegistry

from .models import Question, ValidationStatus
from .registry import QuestionBankRegistry


class QuestionValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    passed: bool
    checks: dict[str, bool]
    failure_reasons: list[str]


class QuestionBankValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isa95_level: str
    total_questions: int
    validated_count: int
    failed_count: int
    results: list[QuestionValidationResult]

    @property
    def all_validated(self) -> bool:
        return self.failed_count == 0 and self.total_questions > 0


def validate_question(question: Question, task_registry: BenchmarkTaskRegistry) -> QuestionValidationResult:
    """
    Runs the Section 25 checklist for one question. Every check here
    reads ONLY already-real, already-loaded data (the question itself,
    its realized BenchmarkTask(s)) -- never invents a new evaluation
    mechanism.
    """

    checks: dict[str, bool] = {}
    reasons: list[str] = []

    # 1. answer is grounded in benchmark data -- every realization must
    #    declare SOME expected evidence to check against.
    realized_tasks = []
    for scenario_id, task_id in question.realizations.items():
        try:
            realized_tasks.append(task_registry.get(task_id))
        except KeyError:
            reasons.append(f"realization for scenario {scenario_id!r} references unknown task {task_id!r}")
    checks["realizations_resolve_to_real_tasks"] = len(realized_tasks) == len(question.realizations)

    grounded = all(bool(t.required_evidence) or bool(t.expected_entities) for t in realized_tasks)
    checks["answer_is_grounded_in_benchmark_data"] = grounded and bool(realized_tasks)
    if not grounded:
        reasons.append("at least one realized task declares no required_evidence/expected_entities to ground an answer in")

    # 2. correct ISA-95 level -- already enforced by QuestionBankRegistry
    #    at construction time, re-asserted here for a self-contained report.
    level_ok = all(t.isa95_level is None or t.isa95_level == question.isa95_level for t in realized_tasks)
    checks["correct_isa95_level"] = level_ok
    if not level_ok:
        reasons.append("a realized task's own isa95_level disagrees with the question's")

    # 3. expected evidence exists (non-trivial description + at least one real task backing it).
    checks["expected_evidence_documented"] = bool(question.expected_evidence_description.strip())

    # 4. expected answer is deterministic enough to evaluate -- every
    #    realized task's binding_scores must be real, known evaluator fields.
    scores_known = all(
        set(t.evaluation_criteria.binding_scores) <= set(KNOWN_SCORE_FIELDS) for t in realized_tasks
    )
    checks["answer_is_deterministically_evaluable"] = scores_known and bool(realized_tasks)

    # 5. compatible scenario exists -- realized_tasks resolving at all (check 1) implies this.
    checks["compatible_scenario_exists"] = checks["realizations_resolve_to_real_tasks"]

    # 6. context hypothesis is documented.
    checks["context_hypothesis_documented"] = len(question.hypothesized_required_context) > 0

    # 7. evaluator can score it -- every realized task declares >=1 binding score.
    checks["evaluator_can_score_it"] = all(len(t.evaluation_criteria.binding_scores) > 0 for t in realized_tasks) and bool(realized_tasks)

    # 8. question is not a duplicate -- enforced by QuestionBankRegistry's
    #    own construction (a duplicate question_id raises before this
    #    function is ever reached); reported as trivially true here for
    #    a complete, self-describing checklist.
    checks["not_a_duplicate"] = True

    passed = all(checks.values())
    return QuestionValidationResult(question_id=question.question_id, passed=passed, checks=checks, failure_reasons=reasons)


def validate_question_bank(registry: QuestionBankRegistry, task_registry: BenchmarkTaskRegistry, isa95_level: str) -> QuestionBankValidationReport:
    results = [validate_question(question, task_registry) for question in registry]
    validated = sum(1 for r in results if r.passed)
    return QuestionBankValidationReport(
        isa95_level=isa95_level,
        total_questions=len(results),
        validated_count=validated,
        failed_count=len(results) - validated,
        results=results,
    )
