"""Unit tests for `icab.tasks.experiment_design` -- the design-strategy generators (Phase 4 of the ICAB v2 context-requirement direction)."""

from __future__ import annotations

import pytest

from icab.tasks.context_combinations import combination_for_id
from icab.tasks.context_dimensions import ContextDimension
from icab.tasks.experiment_design import (
    DesignStrategy,
    ablation_conditions,
    generate_conditions,
    pairwise_conditions,
    progressive_conditions,
    single_dimension_conditions,
    targeted_conditions,
)


class TestSingleDimension:
    def test_returns_exactly_the_seven_dimensions(self):
        conditions = single_dimension_conditions()

        assert len(conditions) == 7
        assert {c.combination_id for c in conditions} == {"C1", "C2", "C3", "C4", "C5", "C6", "C7"}
        assert all(c.cardinality == 1 for c in conditions)


class TestPairwise:
    def test_returns_all_21_pairs(self):
        conditions = pairwise_conditions()

        assert len(conditions) == 21
        assert all(c.cardinality == 2 for c in conditions)
        assert combination_for_id("C1+C2") in conditions
        assert combination_for_id("C6+C7") in conditions

    def test_no_duplicates(self):
        ids = [c.combination_id for c in pairwise_conditions()]
        assert len(ids) == len(set(ids))


class TestProgressive:
    def test_default_order_is_canonical_and_cumulative(self):
        conditions = progressive_conditions()

        assert [c.combination_id for c in conditions] == [
            "C1", "C1+C2", "C1+C2+C3", "C1+C2+C3+C4",
            "C1+C2+C3+C4+C5", "C1+C2+C3+C4+C5+C6", "C1+C2+C3+C4+C5+C6+C7",
        ]
        assert [c.cardinality for c in conditions] == [1, 2, 3, 4, 5, 6, 7]

    def test_custom_order_is_respected(self):
        order = [
            ContextDimension.C4_TEMPORAL,
            ContextDimension.C1_SEMANTIC,
            ContextDimension.C5_OPERATIONAL,
            ContextDimension.C2_ASSET_HIERARCHY,
            ContextDimension.C3_RELATIONAL,
            ContextDimension.C6_PROCEDURAL,
            ContextDimension.C7_HISTORICAL,
        ]
        conditions = progressive_conditions(order)

        assert conditions[0].combination_id == "C4"
        assert conditions[1].combination_id == "C1+C4"  # canonical id ordering, regardless of prefix order
        assert conditions[-1].combination_id == "C1+C2+C3+C4+C5+C6+C7"

    def test_incomplete_order_is_rejected(self):
        with pytest.raises(ValueError):
            progressive_conditions([ContextDimension.C1_SEMANTIC, ContextDimension.C2_ASSET_HIERARCHY])


class TestTargeted:
    def test_returns_exactly_the_named_combinations_in_order(self):
        conditions = targeted_conditions(["C1+C2+C3+C4+C5+C6+C7", "C5"])

        assert [c.combination_id for c in conditions] == ["C1+C2+C3+C4+C5+C6+C7", "C5"]

    def test_unknown_id_raises(self):
        with pytest.raises(KeyError):
            targeted_conditions(["not-a-real-id"])


class TestAblation:
    def test_baseline_plus_one_removal_per_dimension(self):
        baseline = combination_for_id("C1+C2+C3")
        conditions = ablation_conditions(baseline)

        assert [c.combination_id for c in conditions] == ["C1+C2+C3", "C2+C3", "C1+C3", "C1+C2"]

    def test_full_seven_dimension_baseline_yields_eight_conditions(self):
        baseline = combination_for_id("C1+C2+C3+C4+C5+C6+C7")
        conditions = ablation_conditions(baseline)

        assert len(conditions) == 8  # baseline + 7 single-dimension removals
        assert conditions[0] == baseline

    def test_single_dimension_baseline_has_nothing_to_remove(self):
        baseline = combination_for_id("C5")
        conditions = ablation_conditions(baseline)

        assert conditions == (baseline,)


class TestGenerateConditionsDispatch:
    def test_single(self):
        assert len(generate_conditions(DesignStrategy.SINGLE)) == 7

    def test_pairwise(self):
        assert len(generate_conditions("pairwise")) == 21

    def test_progressive(self):
        assert len(generate_conditions("progressive")) == 7

    def test_targeted_requires_targets(self):
        with pytest.raises(ValueError):
            generate_conditions("targeted")

    def test_targeted_with_targets(self):
        conditions = generate_conditions("targeted", targets=["C5"])
        assert conditions[0].combination_id == "C5"

    def test_ablation_requires_baseline(self):
        with pytest.raises(ValueError):
            generate_conditions("ablation")

    def test_ablation_with_baseline_id(self):
        conditions = generate_conditions("ablation", baseline="C1+C2")
        assert conditions[0].combination_id == "C1+C2"

    def test_replay_is_not_dispatchable_here(self):
        with pytest.raises(ValueError):
            generate_conditions("replay")

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            generate_conditions("not-a-real-strategy")
