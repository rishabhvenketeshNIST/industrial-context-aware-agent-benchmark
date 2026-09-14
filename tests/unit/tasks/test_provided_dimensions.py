"""ICAB v2: tests for `provided_dimensions` -- what an architecture ARM makes available, distinct from what a task requires."""

from __future__ import annotations

from icab.tasks.context_dimensions import ContextDimension, provided_dimensions
from icab.tasks.isa95 import ISA95_LEVEL_ORDER, ISA95Level


class TestProvidedDimensions:
    def test_historian_alone_provides_temporal_operational_historical(self):
        provided = set(provided_dimensions(["historian"]))
        assert provided == {ContextDimension.C4_TEMPORAL, ContextDimension.C5_OPERATIONAL, ContextDimension.C7_HISTORICAL}

    def test_knowledge_graph_alone_provides_hierarchy_relational_and_procedural(self):
        # C2 (Asset/Hierarchy) is ALSO knowledge_graph-supportable per
        # CONTEXT_DIMENSION_ARCHITECTURES (alongside uns/opcua/i3x) --
        # confirmed directly here rather than assumed.
        provided = set(provided_dimensions(["knowledge_graph"]))
        assert provided == {
            ContextDimension.C2_ASSET_HIERARCHY,
            ContextDimension.C3_RELATIONAL,
            ContextDimension.C6_PROCEDURAL,
        }

    def test_uns_alone_provides_semantic_and_hierarchy(self):
        provided = set(provided_dimensions(["uns"]))
        assert provided == {ContextDimension.C1_SEMANTIC, ContextDimension.C2_ASSET_HIERARCHY}

    def test_i3x_alone_provides_every_dimension(self):
        # i3x is architecturally capable of all seven per
        # CONTEXT_DIMENSION_ARCHITECTURES -- a real, documented fact
        # about i3X's broad tool surface, not an assumption.
        assert set(provided_dimensions(["i3x"])) == set(ContextDimension)

    def test_combining_architectures_unions_their_provided_dimensions(self):
        historian_only = set(provided_dimensions(["historian"]))
        kg_only = set(provided_dimensions(["knowledge_graph"]))
        combined = set(provided_dimensions(["historian", "knowledge_graph"]))
        assert combined == historian_only | kg_only

    def test_provided_dimensions_differs_from_a_tasks_fixed_required_dimensions(self):
        """
        The whole point of `provided_dimensions`: it varies with the
        architecture ARM, unlike a task's own required_context_dimensions
        (fixed regardless of which arm ran it) -- running the same task
        with a narrower architecture arm changes what was PROVIDED.
        """

        full_arm = provided_dimensions(["historian", "knowledge_graph", "uns"])
        narrow_arm = provided_dimensions(["historian"])
        assert set(narrow_arm) < set(full_arm)


class TestISA95Level:
    def test_six_levels_matching_the_existing_cim_entity_hierarchy(self):
        assert [level.value for level in ISA95_LEVEL_ORDER] == [
            "enterprise", "site", "area", "work_center", "process_cell", "equipment",
        ]

    def test_values_match_the_documented_yaml_spelling(self):
        # The ICAB v2 direction's own examples use `isa95_level: process_cell`
        # / `isa95_level: equipment` -- confirm the enum values match exactly.
        assert ISA95Level.PROCESS_CELL.value == "process_cell"
        assert ISA95Level.EQUIPMENT.value == "equipment"
