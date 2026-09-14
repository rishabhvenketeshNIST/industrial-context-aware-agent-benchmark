"""
ICAB v2: deterministic experimental-design strategies over the 127-
combination context space (`icab.tasks.context_combinations`) -- which
context CONDITIONS to test, kept strictly separate from whether/how they
can actually be RUN (`icab.tasks.context_conditions` resolves that) or
whether they've already been run (`icab.analysis._shared
.tested_combination_ids` answers that from persisted records).

None of these functions execute anything, call a registry, or touch
`results/` -- they are pure generators over `ALL_CONTEXT_COMBINATIONS`,
independently testable without any infrastructure. This module
deliberately never claims "the full 127-combination space was tested" --
each strategy is a small, explicit, human-chosen SUBSET, exactly per the
ICAB v2 direction: "support the full space while allowing experimental
designs to select subsets."
"""

from __future__ import annotations

from enum import StrEnum
from typing import Sequence

from .context_combinations import (
    CANONICAL_DIMENSION_ORDER,
    ContextCombination,
    combination_for_dimensions,
    combination_for_id,
)
from .context_dimensions import ContextDimension


class DesignStrategy(StrEnum):
    """The five static selection strategies this module supports, plus REPLAY (handled by the caller -- see module docstring)."""

    SINGLE = "single"
    PAIRWISE = "pairwise"
    PROGRESSIVE = "progressive"
    TARGETED = "targeted"
    ABLATION = "ablation"
    REPLAY = "replay"


def single_dimension_conditions() -> tuple[ContextCombination, ...]:
    """The 7 cardinality-1 combinations: "what can each context dimension provide independently?" """

    return tuple(combo for combo in _all() if combo.cardinality == 1)


def pairwise_conditions() -> tuple[ContextCombination, ...]:
    """All C(7,2) = 21 cardinality-2 combinations: "which dimensions provide complementary value?" """

    return tuple(combo for combo in _all() if combo.cardinality == 2)


def progressive_conditions(
    order: Sequence[ContextDimension] | None = None,
) -> tuple[ContextCombination, ...]:
    """
    Cumulative prefixes of `order` (default: the canonical C1..C7 order) --
    7 combinations of cardinality 1, 2, ..., 7, each a superset of the
    last, for investigating marginal benefit as context is added
    incrementally.
    """

    sequence = tuple(order) if order is not None else CANONICAL_DIMENSION_ORDER
    if set(sequence) != set(CANONICAL_DIMENSION_ORDER) or len(sequence) != len(CANONICAL_DIMENSION_ORDER):
        raise ValueError(
            f"progressive_conditions order must be a permutation of all seven dimensions, got: {list(sequence)}"
        )

    return tuple(
        combination_for_dimensions(sequence[: prefix_length])
        for prefix_length in range(1, len(sequence) + 1)
    )


def targeted_conditions(combination_ids: Sequence[str]) -> tuple[ContextCombination, ...]:
    """An explicit, caller-chosen list of combination ids -- for a focused experiment. Raises KeyError on an unknown id (via `combination_for_id`), never silently drops one."""

    return tuple(combination_for_id(combination_id) for combination_id in combination_ids)


def ablation_conditions(baseline: ContextCombination) -> tuple[ContextCombination, ...]:
    """
    The baseline itself, followed by one combination per single dimension
    REMOVED from it (baseline's own dimensions minus one, for each
    dimension baseline contains) -- e.g. for baseline C1+C2+C3, this
    yields (C1+C2+C3, C2+C3, C1+C3, C1+C2).

    A baseline of cardinality 1 has nothing left to remove without
    becoming empty (a context combination is never allowed to be empty --
    see `icab.tasks.context_combinations`), so its ablation set is just
    itself; the caller is expected to have already chosen a genuinely
    non-trivial baseline (a broader combination, e.g. a use case's
    candidate_context or the maximal combination actually achievable for
    a task) for this to be scientifically useful.
    """

    conditions = [baseline]
    for removed in baseline.dimensions:
        remaining = [d for d in baseline.dimensions if d != removed]
        if remaining:
            conditions.append(combination_for_dimensions(remaining))
    return tuple(conditions)


def generate_conditions(
    strategy: DesignStrategy | str,
    *,
    targets: Sequence[str] | None = None,
    baseline: ContextCombination | str | None = None,
    progressive_order: Sequence[ContextDimension] | None = None,
) -> tuple[ContextCombination, ...]:
    """
    Single dispatch point over the five static strategies -- REPLAY is
    NOT handled here (it depends on already-persisted records, which this
    module has no access to; see `icab.analysis._shared
    .tested_combination_ids` and `icab.benchmark.context_experiment` for
    where replay is actually resolved).
    """

    strategy = DesignStrategy(strategy)

    if strategy == DesignStrategy.SINGLE:
        return single_dimension_conditions()
    if strategy == DesignStrategy.PAIRWISE:
        return pairwise_conditions()
    if strategy == DesignStrategy.PROGRESSIVE:
        return progressive_conditions(progressive_order)
    if strategy == DesignStrategy.TARGETED:
        if not targets:
            raise ValueError("DesignStrategy.TARGETED requires a non-empty `targets` list of combination ids.")
        return targeted_conditions(targets)
    if strategy == DesignStrategy.ABLATION:
        if baseline is None:
            raise ValueError("DesignStrategy.ABLATION requires a `baseline` ContextCombination or combination id.")
        resolved_baseline = baseline if isinstance(baseline, ContextCombination) else combination_for_id(baseline)
        return ablation_conditions(resolved_baseline)

    raise ValueError(f"generate_conditions cannot build DesignStrategy.REPLAY -- see module docstring.")


def _all() -> tuple[ContextCombination, ...]:
    from .context_combinations import ALL_CONTEXT_COMBINATIONS

    return ALL_CONTEXT_COMBINATIONS
