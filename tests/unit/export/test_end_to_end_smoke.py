"""
End-to-end smoke test: CLI question-selection -> QuestionBenchmarkRunner
.run() -> ExperimentResultStore -> icab.export build/writer/validation,
the FULL pipeline the ICAB export milestone asked for, wired together
exactly as `scripts/run_level_benchmark.py`'s own `_run_one_level`/
`_export_campaign` do -- with `ExperimentRunner.run_task` mocked (no
real gateway/simulator/LLM call), proving the whole path works together
without launching the real 3,000-execution campaign.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

from icab.agent.interface import EvidenceReference, InvestigationResult
from icab.benchmark.levels import get_level_benchmark
from icab.benchmark.question_runner import QuestionBenchmarkConfig, QuestionBenchmarkRunner
from icab.evaluation.grounded import EvaluationReport
from icab.experiments import (
    ExperimentRecord,
    ExperimentResultStore,
    ExperimentRunner,
    ExperimentRunStatus,
    RunValidity,
    compute_configuration_hash,
)
from icab.export import CampaignExportWriter, build_canonical_record, validate_export
from icab.questions import QuestionBankRegistry
from icab.scenarios import BenchmarkScenarioRegistry
from icab.tasks.isa95 import ISA95Level
from icab.tasks.registry import BenchmarkTaskRegistry
from icab.usecases import IndustrialUseCaseRegistry

SCENARIOS_DIR = "configs/benchmark/scenarios"
TASKS_V2_DIR = "configs/benchmark/tasks_v2"
USECASES_DIR = "configs/usecases"

QUESTION_IDS = ["Q-d1-qa-current-pressure", "Q-d1-qa-current-level"]


def _realistic_run_task(task, config, *, scenario, run_id, experiment_id, benchmark_version, git_commit):
    now = datetime.now(UTC)
    evaluation = EvaluationReport(
        scenario_id=scenario.scenario_id,
        required_evidence_hits={eid: True for eid in task.required_evidence},
        required_evidence_score=1.0,
        evidence_has_valid_provenance=True,
        canonical_id_validity={eid: True for eid in task.required_evidence},
        canonical_id_score=1.0,
        temporal_evidence_required=False,
        temporal_evidence_acquired=False,
        expected_relationships=[],
        relationship_score=1.0,
        root_cause_identified=None,
        affected_assets_mentioned={},
        conclusion_correctness_score=1.0,
        unsupported_numeric_claims=[],
        grounding_score=1.0,
        context_acquired=list(task.required_evidence),
        context_consumed=list(task.required_evidence),
        tool_call_count=1,
        unique_tools_used=["get_measurement"],
        terminated_properly=True,
        completeness_score=1.0,
    )
    result = InvestigationResult(
        objective=task.objective,
        conclusion=task.ground_truth.conclusion,
        evidence=[EvidenceReference(source="historian", identifier=eid) for eid in task.required_evidence],
    )
    record = ExperimentRecord(
        run_id=run_id,
        experiment_id=experiment_id,
        config=config,
        scenario_difficulty=task.difficulty.value,
        simulation_seed=scenario.seed,
        generation_id="smoke-generation-id",
        icab_version="test",
        benchmark_version=benchmark_version,
        git_commit=git_commit,
        fault_id=scenario.faults[0].disturbance if scenario.faults else None,
        scenario_version=scenario.version,
        task_version=task.version,
        configuration_hash=compute_configuration_hash(config),
        started_at=now,
        completed_at=now,
        status=ExperimentRunStatus.COMPLETED,
        validity=RunValidity.VALID,
        result=result,
        evaluation=evaluation,
        information_flow=None,
        trace_event_count=1,
        total_latency_ms=150.0,
    )
    return record, []


class TestFullPipelineSmokeTest:
    def test_execute_persist_export_validate_end_to_end(self, tmp_path):
        experiment_runner = Mock(spec=ExperimentRunner)
        experiment_runner.run_task.side_effect = _realistic_run_task

        scenario_registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
        task_registry = BenchmarkTaskRegistry(TASKS_V2_DIR, scenario_registry=scenario_registry)
        use_case_registry = IndustrialUseCaseRegistry(USECASES_DIR, scenario_registry=scenario_registry)
        definition = get_level_benchmark(ISA95Level.EQUIPMENT)
        question_registry = QuestionBankRegistry(definition.question_bank_dir, use_case_registry=use_case_registry, task_registry=task_registry)

        experiment_store = ExperimentResultStore(root=tmp_path / "results")
        runner = QuestionBenchmarkRunner(
            definition=definition,
            experiment_runner=experiment_runner,
            question_registry=question_registry,
            use_case_registry=use_case_registry,
            task_registry=task_registry,
            scenario_registry=scenario_registry,
            experiment_store=experiment_store,
        )

        # Step 1: dry run first (as the documented user workflow instructs) --
        # no execution, no persistence.
        config = QuestionBenchmarkConfig(question_ids=QUESTION_IDS, agent="baseline", allow_overshoot=True, repetitions=3, name="smoke-campaign")
        plan = runner.plan(config)
        assert plan.planned_executions == 2 * 3
        assert experiment_store.list_run_ids() == []

        # Step 2: execute for real (mocked execution path).
        result = runner.run(config)
        assert result.total_runs == 6
        assert result.successful_runs == 6

        # Step 3: resume -- must add nothing (everything already done).
        resumed = config.model_copy(update={"resume": True})
        resumed_result = runner.run(resumed)
        assert resumed_result.total_runs == 6
        experiment_runner.run_task.assert_called()
        call_count_after_first_run = experiment_runner.run_task.call_count
        runner.run(resumed)  # a second resume call must not add more calls
        assert experiment_runner.run_task.call_count == call_count_after_first_run

        # Step 4: export the standalone dataset.
        canonical_records = []
        for outcome in result.outcomes:
            question = question_registry.get(outcome.question_id)
            task = task_registry.get(question.realizations[outcome.scenario_id])
            for run_id in outcome.run_ids:
                record = experiment_store.load_record(run_id)
                trace = experiment_store.load_trace(run_id)
                canonical_records.append(
                    build_canonical_record(
                        record, trace, question=question, task=task, campaign_id=result.campaign_id,
                        benchmark_name=definition.benchmark_id, benchmark_version=definition.question_bank_version,
                    )
                )
        assert len(canonical_records) == 6

        writer = CampaignExportWriter(output_root=tmp_path / "benchmark_exports")
        campaign_dir = writer.write(
            isa95_level="equipment",
            campaign_id=result.campaign_id,
            records=canonical_records,
            planned_questions=[question_registry.get(qid) for qid in QUESTION_IDS],
            manifest_extra={"repetitions": 3, "agent": "baseline"},
        )

        # Step 5: validate the export is self-contained and internally consistent.
        report = validate_export(campaign_dir)
        assert report.is_valid, report.issues
        assert report.n_executions == 6

        # Step 6: results/ (ICAB's own store) is untouched by the export --
        # separate roots, as required.
        assert (tmp_path / "results").exists()
        assert (tmp_path / "benchmark_exports").exists()
        assert not (tmp_path / "results" / "benchmark_exports").exists()

        # A correctness/evidence/ground-truth spot check on one record.
        first = sorted(canonical_records, key=lambda r: r.execution_id)[0]
        assert first.evaluation.correct is True
        assert first.ground_truth.answer is not None
        assert first.llm.answer is not None
        assert first.evidence.items
