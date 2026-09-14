"""
M13-D: benchmark suite/config declarations -- which real, on-disk
directories back a named suite (``--suite tep-v1``), and how
``--architectures`` selects what architecture arm(s) actually run against
a given `BenchmarkTask`.

This module holds no execution logic itself (see `icab.benchmark.runner`
for that) and reuses M13-A/B/C's own registries/models rather than
re-describing task/scenario content here.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from icab.agent.llm.tools import ARCHITECTURE_TOOL_NAMES
from icab.experiments.architecture_combinations import get_combination, list_combination_keys
from icab.tasks.benchmark_task import BenchmarkTask

#: icab.benchmark's OWN version, distinct from icab_version (the installed
#: icab package version, `icab.experiments.runner._icab_version`) and
#: from individual `BenchmarkScenario.version`/`BenchmarkTask.version` --
#: bump this only if the ORCHESTRATION itself changes in a way that could
#: affect run comparability (e.g. how --seeds is applied to a scenario).
BENCHMARK_SUITE_VERSION = "1.0.0"


@dataclass(frozen=True)
class SuiteConfig:
    """Where one named benchmark suite's scenarios/tasks/splits live on disk."""

    name: str
    scenarios_dir: Path
    tasks_dir: Path
    splits_path: Path


#: The only currently-registered suite. Adding a second suite means adding
#: a new entry here (and its own configs/ directory) -- the M13-D
#: requirement is that the runner load the ACTUAL registered task
#: inventory for a suite rather than hard-coding a task list into the
#: runner itself; this dict is the one place suite->directory mapping is
#: declared, extensible without redesigning the runner.
SUITES: dict[str, SuiteConfig] = {
    "tep-v1": SuiteConfig(
        name="tep-v1",
        scenarios_dir=Path("configs/benchmark/scenarios"),
        tasks_dir=Path("configs/benchmark/tasks"),
        splits_path=Path("configs/benchmark/splits.yaml"),
    ),
}


def get_suite(name: str) -> SuiteConfig:
    try:
        return SUITES[name]
    except KeyError:
        raise KeyError(f"Unknown benchmark suite: {name!r}. Valid: {sorted(SUITES)}") from None


def get_git_commit() -> str | None:
    """
    Best-effort ``git rev-parse HEAD`` at the current working directory,
    for `ExperimentRecord.git_commit` audit trail. Returns None (rather
    than raising) outside a git repository, when git isn't on PATH, or on
    any other failure -- this is an audit convenience, not something the
    benchmark run should ever fail over.
    """

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    commit = result.stdout.strip()
    return commit or None


@dataclass(frozen=True)
class ArchitectureArm:
    """One resolved architecture arm to run: the tool-availability list actually enforced, plus its label."""

    architectures: tuple[str, ...]
    combination_key: str | None


def resolve_architecture_arms(spec: str, task: BenchmarkTask) -> list[ArchitectureArm]:
    """
    Resolve ``--architectures <spec>`` against one ``task``'s own declared
    `available_architectures` -- never against the full universe of
    architectures ICAB happens to know how to talk to. A task must
    actually declare/support an architecture for it to run here; e.g. i3X
    is not "available" merely because the private i3X service exists.

    - ``"all"`` expands to one single-architecture arm per architecture
      the task itself declares available -- the standard
      architecture-as-independent-treatment sweep this benchmark
      compares.
    - a named `icab.experiments.architecture_combinations` key expands to
      one arm using that combination's architectures, ONLY if every one
      of them is in the task's own `available_architectures` --
      otherwise an EMPTY list is returned (the caller must treat this as
      "skip this task for this architecture spec", never as a failure or
      as running a subset silently).
    - anything else is treated as a raw comma-separated architecture
      list -- one arm using exactly those architectures together, again
      only if it's a subset of the task's own `available_architectures`.

    An empty return value always means "no valid arm for this
    (spec, task) pair" -- the caller is responsible for counting that as
    a skipped run, never as an error and never as "run it anyway."
    """

    spec = spec.strip()

    if spec == "all":
        return [
            ArchitectureArm(architectures=(architecture,), combination_key=None)
            for architecture in task.available_architectures
        ]

    if spec in list_combination_keys():
        combination = get_combination(spec)
        if not set(combination.architectures) <= set(task.available_architectures):
            return []
        return [
            ArchitectureArm(
                architectures=tuple(combination.architectures),
                combination_key=combination.key,
            )
        ]

    architectures = tuple(part.strip() for part in spec.split(",") if part.strip())
    if not architectures or not set(architectures) <= set(task.available_architectures):
        return []

    return [ArchitectureArm(architectures=architectures, combination_key=None)]


def validate_architectures_spec(spec: str) -> None:
    """
    Fails fast, with every unrecognized name listed, if ``spec`` names an
    architecture ICAB doesn't know how to talk to AT ALL -- e.g. a typo
    like ``"histroian"``. Deliberately distinct from a KNOWN architecture
    a particular TASK simply doesn't grant (that is a per-task SKIP, not
    a configuration error -- see `resolve_architecture_arms`); this
    check only rules out names that could never be valid for ANY task,
    so it can run once, before task selection, rather than per task.
    """

    spec = spec.strip()

    if spec == "all" or spec in list_combination_keys():
        return

    unknown = [
        name
        for name in (part.strip() for part in spec.split(","))
        if name and name not in ARCHITECTURE_TOOL_NAMES
    ]

    if unknown:
        raise ValueError(
            f"Unknown architecture(s) in --architectures {spec!r}: {unknown}. "
            f"Valid architecture names: {sorted(ARCHITECTURE_TOOL_NAMES)}. "
            f"Valid combination keys: {list_combination_keys()}. Or pass 'all'."
        )


class BenchmarkConfig(BaseModel):
    """
    One `run_benchmark.py` invocation's full configuration, reified as an
    explicit, serializable object -- the M13-D "configuration should be
    explicit and reproducible" requirement. Persisted alongside the
    benchmark's report (see `icab.benchmark.runner.BenchmarkRunner`) so a
    benchmark invocation is self-describing, in addition to each
    individual run's own `ExperimentConfig`/`configuration_hash`.
    """

    model_config = ConfigDict(extra="forbid")

    suite: str
    split: str | None = None
    task_id: str | None = None
    scenario_id: str | None = None

    #: "baseline" (ScenarioAwareBaselineAgent) or "llm"
    #: (LLMInvestigationAgent) are the two primary, benchmark-eligible
    #: agents. A `icab.experiments.DeterministicAgentKind` legacy value
    #: (e.g. "structured_retrieval") is also accepted as an EXPLICIT,
    #: separate opt-in for a labeled legacy control -- never the default,
    #: and always recorded/excluded from aggregates the same way
    #: `RunValidity.LEGACY_CONTROL_ONLY` already handles for
    #: `icab.experiments.ExperimentRunner`.
    agent: str = "llm"

    #: See `resolve_architecture_arms` for exactly what this string means.
    architectures: str = "all"

    seeds: list[int] | None = None
    #: Must be >= 1 -- a `--repetitions 0` (or negative) would otherwise
    #: silently produce ZERO runs for every (task, architecture arm,
    #: seed) combination (an empty `range(1, repetitions + 1)`), with no
    #: error and no skipped-run count either. Rejected at construction
    #: time instead, with pydantic's own clear message.
    repetitions: int = Field(default=1, ge=1)

    llm_model: str | None = None
    llm_temperature: float | None = None
    #: All four budgets must be positive when set -- a non-positive
    #: budget doesn't crash (LLMInvestigationAgent degrades gracefully to
    #: an immediate *_BUDGET_EXCEEDED result), but it is never a useful
    #: benchmark configuration and is almost always a typo, so it is
    #: rejected here as a clear configuration error instead.
    max_steps: int | None = Field(default=None, ge=1)
    max_tool_calls: int | None = Field(default=None, ge=1)
    max_context_tokens: int | None = Field(default=None, ge=1)
    max_wall_time_seconds: float | None = Field(default=None, gt=0)

    #: Overrides the auto-generated benchmark/experiment id.
    name: str | None = None

    #: Production-safety guard: refuse to run when `results/` already
    #: contains artifacts for this exact benchmark_id (see
    #: BenchmarkRunner._check_no_existing_benchmark) -- only relevant
    #: when `name` is explicitly set, since the auto-generated
    #: `benchmark-<suite>-<uuid>` id is never reused. Pass `force=True`
    #: to deliberately overwrite anyway (e.g. iterating on a smoke test
    #: during development).
    force: bool = False
