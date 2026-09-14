"""
ICAB v3 50-question milestone (Sections 19-20): the 3,000-execution
invariant checker and per-level completeness report.

    6 levels x 50 unique questions x 10 repetitions = 3,000 executions

This module NEVER reports 100%/complete unless every one of the checks
below genuinely passes -- a partial campaign stays visibly, structurally
incomplete (`CompletenessReport.is_complete=False`), never silently
rounded up.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord, ExperimentRunStatus
from icab.questions import QuestionBankRegistry

#: The milestone's own fixed targets -- not hard-coded into every call
#: site, but the single, explicit source of truth for "complete."
TARGET_QUESTIONS_PER_LEVEL = 50
TARGET_REPETITIONS_PER_QUESTION = 10
TARGET_EXECUTIONS_PER_LEVEL = TARGET_QUESTIONS_PER_LEVEL * TARGET_REPETITIONS_PER_QUESTION
TARGET_LEVEL_COUNT = 6
TARGET_TOTAL_EXECUTIONS = TARGET_EXECUTIONS_PER_LEVEL * TARGET_LEVEL_COUNT


class QuestionCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    repetitions_completed: int  # successful (COMPLETED, VALID) runs, deduplicated by repetition index
    repetitions_target: int = TARGET_REPETITIONS_PER_QUESTION
    complete: bool
    issues: list[str] = []


class LevelCompletenessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isa95_level: str
    benchmark_id: str | None

    n_questions_expected: int = TARGET_QUESTIONS_PER_LEVEL
    n_questions_in_bank: int
    n_questions_validated: int  # distinct question_ids that appear at all in results, regardless of repetition count

    n_executions_expected: int = TARGET_EXECUTIONS_PER_LEVEL
    n_executions_actual: int
    n_executions_successful: int

    questions: list[QuestionCompleteness]

    #: Structural problems detected -- fewer than 50 questions, duplicate
    #: question ids, wrong isa95_level records, missing trace/experiment
    #: id, etc. Non-empty means `is_complete` is False, no matter what
    #: the raw execution count says.
    issues: list[str] = []

    @property
    def is_complete(self) -> bool:
        return (
            not self.issues
            and self.n_questions_in_bank == self.n_questions_expected
            and self.n_executions_successful == self.n_executions_expected
            and all(q.complete for q in self.questions)
        )

    @property
    def completion_fraction(self) -> float:
        return self.n_executions_successful / self.n_executions_expected if self.n_executions_expected else 0.0


class SuiteCompletenessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    levels: list[LevelCompletenessReport]

    @property
    def is_complete(self) -> bool:
        return len(self.levels) == TARGET_LEVEL_COUNT and all(level.is_complete for level in self.levels)

    @property
    def total_questions_expected(self) -> int:
        return TARGET_QUESTIONS_PER_LEVEL * TARGET_LEVEL_COUNT

    @property
    def total_executions_expected(self) -> int:
        return TARGET_TOTAL_EXECUTIONS

    @property
    def total_executions_actual(self) -> int:
        return sum(level.n_executions_successful for level in self.levels)


def check_level_completeness(
    isa95_level: str,
    question_registry: QuestionBankRegistry,
    records: list[ExperimentRecord],
    *,
    benchmark_id: str | None = None,
) -> LevelCompletenessReport:
    """Computed ONLY from already-persisted records + the real question bank -- never a hand-maintained count."""

    issues: list[str] = []

    bank_ids = question_registry.list_ids()
    if len(bank_ids) != TARGET_QUESTIONS_PER_LEVEL:
        issues.append(f"question bank has {len(bank_ids)} questions, expected exactly {TARGET_QUESTIONS_PER_LEVEL}")
    if len(bank_ids) != len(set(bank_ids)):
        issues.append("duplicate question_ids detected in the question bank")

    # Wrong-level contamination -- every record in this level's results/
    # must declare this exact isa95_level.
    mismatched = [r.run_id for r in records if r.config.isa95_level != isa95_level]
    if mismatched:
        issues.append(f"{len(mismatched)} record(s) have a mismatched isa95_level: {mismatched[:5]}{'...' if len(mismatched) > 5 else ''}")

    missing_trace_or_experiment_id = [
        r.run_id for r in records if not r.experiment_id or r.trace_event_count is None
    ]
    if missing_trace_or_experiment_id:
        issues.append(f"{len(missing_trace_or_experiment_id)} record(s) missing experiment_id/trace reference")

    scoped = [r for r in records if r.config.isa95_level == isa95_level]

    by_question: dict[str, list[ExperimentRecord]] = defaultdict(list)
    for r in scoped:
        if r.config.question_id:
            by_question[r.config.question_id].append(r)

    # duplicate repetitions: the same (question_id, repetition) index run
    # more than once under the SAME instance -- not itself an error (a
    # re-run is legitimate), but flagged for visibility.
    duplicate_repetitions = 0
    for qid, recs in by_question.items():
        by_instance_rep: Counter = Counter((r.config.question_instance_id, r.config.repetition) for r in recs)
        duplicate_repetitions += sum(1 for count in by_instance_rep.values() if count > 1)
    if duplicate_repetitions:
        issues.append(f"{duplicate_repetitions} duplicate (instance, repetition) execution(s) detected")

    question_reports: list[QuestionCompleteness] = []
    for qid in bank_ids:
        recs = by_question.get(qid, [])
        successful_reps = {
            r.config.repetition
            for r in recs
            if r.status == ExperimentRunStatus.COMPLETED and r.config.repetition is not None
        }
        n_completed = len(successful_reps)
        q_issues = []
        if n_completed < TARGET_REPETITIONS_PER_QUESTION:
            q_issues.append(f"only {n_completed}/{TARGET_REPETITIONS_PER_QUESTION} repetitions completed")
        question_reports.append(
            QuestionCompleteness(
                question_id=qid,
                repetitions_completed=n_completed,
                complete=n_completed >= TARGET_REPETITIONS_PER_QUESTION,
                issues=q_issues,
            )
        )

    n_executions_actual = len(scoped)
    n_executions_successful = sum(1 for r in scoped if r.status == ExperimentRunStatus.COMPLETED)
    n_questions_validated = len(by_question)

    return LevelCompletenessReport(
        isa95_level=isa95_level,
        benchmark_id=benchmark_id,
        n_questions_in_bank=len(bank_ids),
        n_questions_validated=n_questions_validated,
        n_executions_actual=n_executions_actual,
        n_executions_successful=n_executions_successful,
        questions=question_reports,
        issues=issues,
    )


def render_completeness_table(report: SuiteCompletenessReport) -> str:
    lines = []
    header = f"{'Level':<14}{'Questions':>16}{'Executions':>18}"
    lines.append(header)
    lines.append("-" * len(header))
    for level in report.levels:
        q_col = f"{level.n_questions_in_bank}/{level.n_questions_expected}"
        e_col = f"{level.n_executions_successful}/{level.n_executions_expected}"
        lines.append(f"{level.isa95_level:<14}{q_col:>16}{e_col:>18}")
    lines.append("-" * len(header))
    total_q = sum(level.n_questions_in_bank for level in report.levels)
    total_e = report.total_executions_actual
    lines.append(f"{'TOTAL':<14}{f'{total_q}/{report.total_questions_expected}':>16}{f'{total_e}/{report.total_executions_expected}':>18}")
    lines.append("")
    lines.append(f"COMPLETE: {report.is_complete}")
    return "\n".join(lines)
