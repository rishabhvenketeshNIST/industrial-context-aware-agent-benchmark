"""
Unit tests for `icab.tasks.context_conditions` -- resolving a target
context combination into a real architecture arm, against the REAL
`CONTEXT_DIMENSION_ARCHITECTURES` mapping (not a fabricated one), so
these tests double as a regression check on that mapping's actual
realizability properties.
"""

from __future__ import annotations

import pytest

from icab.tasks.context_combinations import combination_for_id
from icab.tasks.context_conditions import ConditionStatus, realizable_combinations, resolve_condition_architectures
from icab.tasks.context_dimensions import ContextDimension


class TestExactResolution:
    def test_c5_is_exactly_realizable_via_mqtt_alone(self):
        resolution = resolve_condition_architectures(combination_for_id("C5"), ["historian", "knowledge_graph", "uns", "opcua", "mqtt", "i3x"])

        assert resolution.status == ConditionStatus.EXACT
        assert resolution.architectures == ("mqtt",)
        assert resolution.provided_dimensions == (ContextDimension.C5_OPERATIONAL,)
        assert resolution.extra_dimensions == ()
        assert resolution.architecture_spec == "mqtt"

    def test_full_seven_dimensions_is_exact_via_i3x_alone(self):
        resolution = resolve_condition_architectures(
            combination_for_id("C1+C2+C3+C4+C5+C6+C7"), ["historian", "knowledge_graph", "i3x"]
        )

        assert resolution.status == ConditionStatus.EXACT
        assert resolution.architectures == ("i3x",)

    def test_prefers_the_smallest_exact_arm(self):
        # Both {historian} alone and {historian, mqtt} together provide
        # exactly C4+C5+C7 (mqtt's C5 is already covered by historian) --
        # the smaller arm must be chosen.
        resolution = resolve_condition_architectures(combination_for_id("C4+C5+C7"), ["historian", "mqtt"])

        assert resolution.status == ConditionStatus.EXACT
        assert resolution.architectures == ("historian",)


class TestOvershootResolution:
    def test_c1_alone_overshoots_via_uns(self):
        resolution = resolve_condition_architectures(combination_for_id("C1"), ["uns", "opcua", "historian"])

        assert resolution.status == ConditionStatus.OVERSHOOT
        assert resolution.architectures == ("uns",)
        assert resolution.extra_dimensions == (ContextDimension.C2_ASSET_HIERARCHY,)
        assert ContextDimension.C1_SEMANTIC in resolution.provided_dimensions

    def test_c3_alone_overshoots_via_knowledge_graph_not_i3x(self):
        # i3x would overshoot by 6 extra dimensions; knowledge_graph only by 2 (C2, C6).
        resolution = resolve_condition_architectures(combination_for_id("C3"), ["knowledge_graph", "i3x"])

        assert resolution.status == ConditionStatus.OVERSHOOT
        assert resolution.architectures == ("knowledge_graph",)
        assert set(resolution.extra_dimensions) == {ContextDimension.C2_ASSET_HIERARCHY, ContextDimension.C6_PROCEDURAL}

    def test_minimal_overshoot_prefers_fewer_extra_dimensions_over_fewer_architectures(self):
        # {uns} alone overshoots C1+C2 by 1 extra dim (C2); {uns, historian}
        # together overshoot by 3 (C2, C4, C7) -- fewer extras must win even
        # though it means naming an arm with equal architecture count.
        resolution = resolve_condition_architectures(combination_for_id("C1"), ["uns", "historian"])

        assert resolution.architectures == ("uns",)
        assert len(resolution.extra_dimensions) == 1


class TestUnrealizable:
    def test_c1_is_unrealizable_with_only_historian_available(self):
        resolution = resolve_condition_architectures(combination_for_id("C1"), ["historian"])

        assert resolution.status == ConditionStatus.UNREALIZABLE
        assert resolution.architectures is None
        assert resolution.provided_dimensions == ()
        assert resolution.architecture_spec is None

    def test_c6_is_unrealizable_with_only_historian_and_mqtt(self):
        resolution = resolve_condition_architectures(combination_for_id("C6"), ["historian", "mqtt"])

        assert resolution.status == ConditionStatus.UNREALIZABLE


class TestRealizableCombinations:
    def test_full_architecture_universe_reaches_exactly_thirteen_of_the_127(self):
        # A real, important finding (see docs/benchmark/specification-v2.md):
        # each of ICAB's six architectures supplies MORE than one context
        # dimension, so most of the 127-combination space is unreachable by
        # architecture selection alone, no matter which subset is chosen.
        combos = realizable_combinations(["historian", "knowledge_graph", "uns", "opcua", "mqtt", "i3x"])

        assert len(combos) == 13
        assert combination_for_id("C5") in combos  # mqtt alone
        assert combination_for_id("C1+C2+C3+C4+C5+C6+C7") in combos  # i3x alone

    def test_single_architecture_reaches_exactly_one_combination(self):
        combos = realizable_combinations(["historian"])

        assert combos == [combination_for_id("C4+C5+C7")]

    def test_empty_architecture_list_reaches_nothing(self):
        assert realizable_combinations([]) == []
