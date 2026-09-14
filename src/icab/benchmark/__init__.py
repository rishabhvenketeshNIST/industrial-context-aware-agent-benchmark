"""
M13-D: one-command ICAB benchmark orchestration -- ties together the
M13-A/B/C process/fault/task foundations and the M9-M12 experiment/
aggregation/reporting infrastructure into a single reproducible
end-to-end run. See `icab.benchmark.runner` for the orchestration itself
and `scripts/run_benchmark.py` for the CLI entry point.
"""

from .completeness import (
    TARGET_EXECUTIONS_PER_LEVEL,
    TARGET_QUESTIONS_PER_LEVEL,
    TARGET_REPETITIONS_PER_QUESTION,
    TARGET_TOTAL_EXECUTIONS,
    LevelCompletenessReport,
    QuestionCompleteness,
    SuiteCompletenessReport,
    check_level_completeness,
    render_completeness_table,
)
from .config import (
    BENCHMARK_SUITE_VERSION,
    ArchitectureArm,
    BenchmarkConfig,
    SuiteConfig,
    get_git_commit,
    get_suite,
    resolve_architecture_arms,
)
from .context_experiment import (
    ContextConditionOutcome,
    ContextExperimentConfig,
    ContextExperimentResult,
    ContextExperimentRunner,
)
from .levels import LEVEL_BENCHMARKS, ISA95BenchmarkDefinition, executable_levels, get_level_benchmark
from .manifest import BenchmarkManifest, build_manifest, write_manifest
from .question_runner import (
    IsaLevelMismatchError,
    QuestionBenchmarkConfig,
    QuestionBenchmarkResult,
    QuestionBenchmarkRunner,
    QuestionRunOutcome,
)
from .runner import BenchmarkIdCollisionError, BenchmarkRunner, BenchmarkRunResult

__all__ = [
    "BENCHMARK_SUITE_VERSION",
    "LEVEL_BENCHMARKS",
    "TARGET_EXECUTIONS_PER_LEVEL",
    "TARGET_QUESTIONS_PER_LEVEL",
    "TARGET_REPETITIONS_PER_QUESTION",
    "TARGET_TOTAL_EXECUTIONS",
    "ArchitectureArm",
    "BenchmarkConfig",
    "BenchmarkIdCollisionError",
    "BenchmarkManifest",
    "BenchmarkRunResult",
    "BenchmarkRunner",
    "ContextConditionOutcome",
    "ContextExperimentConfig",
    "ContextExperimentResult",
    "ContextExperimentRunner",
    "ISA95BenchmarkDefinition",
    "IsaLevelMismatchError",
    "LevelCompletenessReport",
    "QuestionBenchmarkConfig",
    "QuestionBenchmarkResult",
    "QuestionBenchmarkRunner",
    "QuestionCompleteness",
    "QuestionRunOutcome",
    "SuiteConfig",
    "SuiteCompletenessReport",
    "build_manifest",
    "check_level_completeness",
    "executable_levels",
    "get_git_commit",
    "get_level_benchmark",
    "get_suite",
    "render_completeness_table",
    "resolve_architecture_arms",
    "write_manifest",
]
