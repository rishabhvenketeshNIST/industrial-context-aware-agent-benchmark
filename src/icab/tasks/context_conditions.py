"""
ICAB v2 (context-requirement experimentation): resolves a TARGET context
combination (`icab.tasks.context_combinations.ContextCombination`) into an
actual ARCHITECTURE ARM that can be handed to
`icab.benchmark.config.resolve_architecture_arms`/`BenchmarkConfig
.architectures` -- the missing forward direction the existing v2 machinery
did not have: `provided_dimensions(architectures)` goes architectures ->
dimensions; this module goes the other way, dimensions -> architectures.

This direction is NOT always possible cleanly, and this module's whole
point is to say so honestly rather than silently overshoot or refuse to
run. Each of ICAB's six architectures supplies more than one context
dimension (see `CONTEXT_DIMENSION_ARCHITECTURES`), so most of the 127
possible dimension combinations cannot be realized EXACTLY by any subset
of them -- e.g. no architecture supplies C3 (Relational) alone; the only
two that supply C3 at all (`knowledge_graph`, `i3x`) always bring C2/C6 or
every other dimension along with it. A caller asking to test "C3 alone"
will get told this plainly (`ConditionStatus.UNREALIZABLE` or
`OVERSHOOT`, never a silent substitution).

Three outcomes, in order of preference:

  * ``EXACT`` -- some subset of the given architectures provides exactly
    the target dimensions, no more, no less. The smallest such subset is
    returned (ties broken alphabetically, for determinism).
  * ``OVERSHOOT`` -- no subset is exact, but some subset's provided
    dimensions are a proper SUPERSET of the target (the target is
    reachable, just not in isolation). The minimal-overshoot subset is
    returned (fewest extra dimensions, ties broken by architecture count
    then alphabetically).
  * ``UNREALIZABLE`` -- not even the FULL given architecture set's
    provided dimensions cover the target (at least one target dimension
    has no architecture, among those given, capable of it at all). No
    architecture arm is returned.

Callers (`icab.tasks.experiment_design`, `icab.benchmark.context_experiment`)
must never silently treat OVERSHOOT as if it were the requested condition,
and must never execute (or hide) an UNREALIZABLE one.
"""

from __future__ import annotations

from enum import StrEnum
from itertools import combinations
from typing import Sequence

from pydantic import BaseModel, ConfigDict

from .context_combinations import ContextCombination
from .context_dimensions import ContextDimension, provided_dimensions


class ConditionStatus(StrEnum):
    """Whether/how a target context combination can be realized by an architecture arm."""

    EXACT = "exact"
    OVERSHOOT = "overshoot"
    UNREALIZABLE = "unrealizable"


class ArchitectureResolution(BaseModel):
    """The result of resolving one `ContextCombination` against one task's `available_architectures`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    combination_id: str
    requested_dimensions: tuple[ContextDimension, ...]
    status: ConditionStatus

    #: The resolved architecture arm -- None only when status == UNREALIZABLE.
    architectures: tuple[str, ...] | None
    #: What that arm actually provides (icab.tasks.context_dimensions
    #: .provided_dimensions) -- equal to requested_dimensions when EXACT,
    #: a proper superset when OVERSHOOT, empty tuple when UNREALIZABLE.
    provided_dimensions: tuple[ContextDimension, ...]
    #: provided_dimensions - requested_dimensions, as combination-id-style
    #: dimension values -- always empty when EXACT.
    extra_dimensions: tuple[ContextDimension, ...]

    reason: str

    @property
    def architecture_spec(self) -> str | None:
        """
        A raw comma-separated string ready to pass as
        `icab.benchmark.config.resolve_architecture_arms`'s `spec` /
        `BenchmarkConfig.architectures` -- None when UNREALIZABLE.
        """

        return ",".join(self.architectures) if self.architectures else None


def resolve_condition_architectures(
    combination: ContextCombination,
    available_architectures: Sequence[str],
) -> ArchitectureResolution:
    """
    Find the best architecture arm, drawn only from `available_architectures`
    (a task's own declared set -- never the full universe of architectures
    ICAB happens to know how to talk to), that realizes `combination`.

    Exhaustive over subsets of `available_architectures`: tasks declare a
    handful of architectures at most (never anywhere near enough for
    2**n to matter), so this is cheap and exact, not a heuristic search.
    """

    target = set(combination.dimensions)
    archs = sorted(set(available_architectures))

    exact_candidates: list[tuple[str, ...]] = []
    overshoot_candidates: list[tuple[tuple[str, ...], frozenset[ContextDimension]]] = []

    for r in range(1, len(archs) + 1):
        for subset in combinations(archs, r):
            provided = frozenset(provided_dimensions(list(subset)))
            if provided == target:
                exact_candidates.append(subset)
            elif provided >= target:
                overshoot_candidates.append((subset, provided))

    if exact_candidates:
        best = min(exact_candidates, key=lambda subset: (len(subset), subset))
        return ArchitectureResolution(
            combination_id=combination.combination_id,
            requested_dimensions=combination.dimensions,
            status=ConditionStatus.EXACT,
            architectures=best,
            provided_dimensions=combination.dimensions,
            extra_dimensions=(),
            reason=f"Architecture arm {list(best)} provides exactly {combination.combination_id}.",
        )

    if overshoot_candidates:
        def _rank(item: tuple[tuple[str, ...], frozenset[ContextDimension]]) -> tuple[int, int, tuple[str, ...]]:
            subset, provided = item
            return (len(provided - target), len(subset), subset)

        best_subset, best_provided = min(overshoot_candidates, key=_rank)
        from .context_combinations import CANONICAL_DIMENSION_ORDER

        provided_ordered = tuple(d for d in CANONICAL_DIMENSION_ORDER if d in best_provided)
        extra = tuple(d for d in CANONICAL_DIMENSION_ORDER if d in (best_provided - target))
        return ArchitectureResolution(
            combination_id=combination.combination_id,
            requested_dimensions=combination.dimensions,
            status=ConditionStatus.OVERSHOOT,
            architectures=best_subset,
            provided_dimensions=provided_ordered,
            extra_dimensions=extra,
            reason=(
                f"No architecture arm drawn from {archs} provides exactly "
                f"{combination.combination_id} in isolation -- the closest "
                f"achievable arm {list(best_subset)} also provides "
                f"{'+'.join(d.value for d in extra)}."
            ),
        )

    return ArchitectureResolution(
        combination_id=combination.combination_id,
        requested_dimensions=combination.dimensions,
        status=ConditionStatus.UNREALIZABLE,
        architectures=None,
        provided_dimensions=(),
        extra_dimensions=(),
        reason=(
            f"No subset of {archs} can supply {combination.combination_id} -- "
            "at least one requested dimension has no architecture, among "
            "those available here, capable of it at all."
        ),
    )


def realizable_combinations(available_architectures: Sequence[str]) -> list[ContextCombination]:
    """
    Every DISTINCT `ContextCombination` that some subset of
    `available_architectures` provides EXACTLY -- i.e. every combination
    reachable at all by architecture selection alone, given these
    architectures. Almost always a small fraction of the full 127-space
    (see module docstring): this is the honest "supported" set for the
    experimental-design layer to draw from, not an assumption that every
    combination is testable.
    """

    from .context_combinations import combination_for_dimensions

    archs = sorted(set(available_architectures))
    seen: dict[frozenset[ContextDimension], ContextCombination] = {}

    for r in range(1, len(archs) + 1):
        for subset in combinations(archs, r):
            provided = frozenset(provided_dimensions(list(subset)))
            if provided and provided not in seen:
                seen[provided] = combination_for_dimensions(provided)

    return sorted(seen.values(), key=lambda combo: (combo.cardinality, combo.combination_id))
