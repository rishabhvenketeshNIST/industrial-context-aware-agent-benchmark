"""ICAB v2: tests for the deterministic 127-combination context-dimension generator."""

from __future__ import annotations

import pytest

from icab.tasks.context_combinations import (
    ALL_CONTEXT_COMBINATIONS,
    CANONICAL_DIMENSION_ORDER,
    combination_for_dimensions,
    combination_for_id,
    combination_id_for,
)
from icab.tasks.context_dimensions import ContextDimension


class TestCompleteness:
    def test_exactly_127_combinations(self):
        assert len(ALL_CONTEXT_COMBINATIONS) == 2**7 - 1 == 127

    def test_no_duplicate_ids(self):
        ids = [combo.combination_id for combo in ALL_CONTEXT_COMBINATIONS]
        assert len(ids) == len(set(ids))

    def test_no_duplicate_dimension_sets(self):
        dimension_sets = [frozenset(combo.dimensions) for combo in ALL_CONTEXT_COMBINATIONS]
        assert len(dimension_sets) == len(set(dimension_sets))

    def test_every_nonempty_subset_of_seven_dimensions_is_present(self):
        from itertools import combinations

        expected = {
            frozenset(dims)
            for r in range(1, 8)
            for dims in combinations(ContextDimension, r)
        }
        actual = {frozenset(combo.dimensions) for combo in ALL_CONTEXT_COMBINATIONS}
        assert actual == expected


class TestCardinality:
    def test_cardinality_matches_dimension_count(self):
        for combo in ALL_CONTEXT_COMBINATIONS:
            assert combo.cardinality == len(combo.dimensions)

    def test_cardinality_distribution_matches_binomial_coefficients(self):
        from collections import Counter
        from math import comb

        counts = Counter(combo.cardinality for combo in ALL_CONTEXT_COMBINATIONS)
        for r in range(1, 8):
            assert counts[r] == comb(7, r)


class TestCanonicalOrdering:
    def test_single_dimension_ids_match_dimension_values(self):
        singles = {combo.combination_id for combo in ALL_CONTEXT_COMBINATIONS if combo.cardinality == 1}
        assert singles == {"C1", "C2", "C3", "C4", "C5", "C6", "C7"}

    def test_combination_id_is_always_in_canonical_order_regardless_of_input_order(self):
        assert combination_id_for([ContextDimension.C4_TEMPORAL, ContextDimension.C1_SEMANTIC]) == "C1+C4"
        assert combination_id_for([ContextDimension.C1_SEMANTIC, ContextDimension.C4_TEMPORAL]) == "C1+C4"

    def test_duplicate_dimensions_are_deduplicated(self):
        assert combination_id_for([ContextDimension.C2_ASSET_HIERARCHY, ContextDimension.C2_ASSET_HIERARCHY]) == "C2"

    def test_full_combination_matches_canonical_dimension_order(self):
        full = combination_for_id("C1+C2+C3+C4+C5+C6+C7")
        assert full.dimensions == CANONICAL_DIMENSION_ORDER
        assert full.cardinality == 7


class TestLookup:
    def test_combination_for_id_round_trips(self):
        for combo in ALL_CONTEXT_COMBINATIONS:
            assert combination_for_id(combo.combination_id) is combo or combination_for_id(combo.combination_id) == combo

    def test_unknown_id_raises_with_a_clear_message(self):
        with pytest.raises(KeyError, match="Unknown context combination"):
            combination_for_id("C9")

    def test_empty_dimensions_raises(self):
        with pytest.raises(ValueError, match="at least one dimension"):
            combination_id_for([])

    def test_combination_for_dimensions_matches_combination_for_id(self):
        dims = [ContextDimension.C3_RELATIONAL, ContextDimension.C7_HISTORICAL]
        assert combination_for_dimensions(dims) == combination_for_id("C3+C7")

    def test_human_readable_name_lists_every_dimension_label(self):
        combo = combination_for_id("C2+C3")
        assert combo.name == "Asset/Hierarchy + Relational"
