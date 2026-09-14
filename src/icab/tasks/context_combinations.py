"""
ICAB v2: the deterministic, complete space of non-empty combinations of
the seven locked context dimensions (`icab.tasks.context_dimensions
.ContextDimension`) -- 2^7 - 1 = 127 combinations, generated (never
hard-coded) so the space is provably complete and every combination has
a stable, canonical id.

This module knows nothing about USE CASES or whether a given combination
is actually meaningful/testable for any particular one -- that
determination (`valid` / `unsupported` / `not_applicable`) is made by
`icab.usecases.classify_combination_for_use_case`, which is a separate,
evidence-driven layer on top of this purely combinatorial one. Conflating
"the combination exists" with "the combination is a meaningful benchmark
condition for use case X" is exactly the mistake the ICAB v2 direction
warns against (do not assume all 127 combinations are meaningful at every
ISA-95 level).
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

from pydantic import BaseModel, ConfigDict

from .context_dimensions import CONTEXT_DIMENSION_LABELS, ContextDimension

#: Canonical ordering -- the enum's own declaration order (C1..C7). Every
#: combination id/dimensions tuple below is built by filtering this
#: sequence, so the id is always dimensions in this fixed order (e.g.
#: "C2+C3", never "C3+C2") regardless of what order a caller passes them in.
CANONICAL_DIMENSION_ORDER: tuple[ContextDimension, ...] = tuple(ContextDimension)


class ContextCombination(BaseModel):
    """One non-empty subset of the seven context dimensions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    combination_id: str
    dimensions: tuple[ContextDimension, ...]
    cardinality: int
    name: str


def _combination_id(dimensions: tuple[ContextDimension, ...]) -> str:
    return "+".join(dimension.value for dimension in dimensions)


def _combination_name(dimensions: tuple[ContextDimension, ...]) -> str:
    return " + ".join(CONTEXT_DIMENSION_LABELS[dimension] for dimension in dimensions)


def _canonical_order(dimensions: Iterable[ContextDimension]) -> tuple[ContextDimension, ...]:
    """Dedupe and sort `dimensions` into `CANONICAL_DIMENSION_ORDER`."""

    wanted = set(dimensions)
    return tuple(dimension for dimension in CANONICAL_DIMENSION_ORDER if dimension in wanted)


def all_context_combinations() -> tuple[ContextCombination, ...]:
    """
    Every non-empty combination of the seven dimensions -- exactly
    2**7 - 1 = 127, ordered first by cardinality (1..7) then by
    `CANONICAL_DIMENSION_ORDER`'s own lexicographic order within each
    cardinality (itertools.combinations over an already-ordered input
    preserves that order, so no separate sort is needed).
    """

    combos: list[ContextCombination] = []
    for cardinality in range(1, len(CANONICAL_DIMENSION_ORDER) + 1):
        for dims in combinations(CANONICAL_DIMENSION_ORDER, cardinality):
            combos.append(
                ContextCombination(
                    combination_id=_combination_id(dims),
                    dimensions=dims,
                    cardinality=cardinality,
                    name=_combination_name(dims),
                )
            )
    return tuple(combos)


#: Computed once, at import time -- the generator above is pure/stateless,
#: so this is safe to cache and is what every lookup below actually uses.
ALL_CONTEXT_COMBINATIONS: tuple[ContextCombination, ...] = all_context_combinations()

_BY_ID: dict[str, ContextCombination] = {combo.combination_id: combo for combo in ALL_CONTEXT_COMBINATIONS}


def combination_id_for(dimensions: Iterable[ContextDimension]) -> str:
    """The canonical id for an arbitrary (possibly unordered, possibly duplicated) set of dimensions."""

    ordered = _canonical_order(dimensions)
    if not ordered:
        raise ValueError("A context combination must contain at least one dimension.")
    return _combination_id(ordered)


def combination_for_id(combination_id: str) -> ContextCombination:
    try:
        return _BY_ID[combination_id]
    except KeyError:
        raise KeyError(
            f"Unknown context combination id: {combination_id!r}. "
            f"Valid ids follow the canonical C1..C7 order, e.g. 'C2+C3', 'C1+C4+C7'."
        ) from None


def combination_for_dimensions(dimensions: Iterable[ContextDimension]) -> ContextCombination:
    return combination_for_id(combination_id_for(dimensions))
