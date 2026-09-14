"""
M13-D: one-command ICAB benchmark orchestration -- ties together the
M13-A/B/C process/fault/task foundations and the M9-M12 experiment/
aggregation/reporting infrastructure into a single reproducible
end-to-end run. See `icab.benchmark.runner` for the orchestration itself
and `scripts/run_benchmark.py` for the CLI entry point.
"""

from .config import (
    BENCHMARK_SUITE_VERSION,
    ArchitectureArm,
    BenchmarkConfig,
    SuiteConfig,
    get_git_commit,
    get_suite,
    resolve_architecture_arms,
)
from .runner import BenchmarkIdCollisionError, BenchmarkRunner, BenchmarkRunResult

__all__ = [
    "BENCHMARK_SUITE_VERSION",
    "ArchitectureArm",
    "BenchmarkConfig",
    "BenchmarkIdCollisionError",
    "BenchmarkRunResult",
    "BenchmarkRunner",
    "SuiteConfig",
    "get_git_commit",
    "get_suite",
    "resolve_architecture_arms",
]
