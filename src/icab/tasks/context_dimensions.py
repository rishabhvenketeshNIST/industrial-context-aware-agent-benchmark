"""
M13-C: the locked ICAB context dimensions (C1-C7) -- what KIND of context
evidence a benchmark task requires, as opposed to WHICH architecture
supplies it (`available_architectures`, a separate declaration).

These are a locked research concept (see the original ICAB build-out
specification); this module is the first place they are given a concrete,
code-level meaning. Per the M13-C direction ("do not assign dimensions
merely because they sound appropriate -- derive them from the actual
evidence/tools the task requires"), each dimension is tied to the
concrete ICAB tools/relationship kinds that actually supply that kind of
evidence, and `architectures_supporting` lets `BenchmarkTask`'s own
validator enforce that a task cannot declare a dimension its own
`available_architectures` has no way to satisfy.

This is a necessary-condition check, not a sufficient one: declaring
`historian` available and C4 Temporal required does not by itself prove
the task's ground truth actually needs a historical query -- that is
established per-task by the fault characterization/scenario ground truth
this task is built from (see icab.tasks.benchmark_task), and, for
representative tasks, by an integration test run against the real stack.
"""

from __future__ import annotations

from enum import StrEnum


class ContextDimension(StrEnum):
    """The seven locked ICAB context dimensions."""

    C1_SEMANTIC = "C1"
    C2_ASSET_HIERARCHY = "C2"
    C3_RELATIONAL = "C3"
    C4_TEMPORAL = "C4"
    C5_OPERATIONAL = "C5"
    C6_PROCEDURAL = "C6"
    C7_HISTORICAL = "C7"


CONTEXT_DIMENSION_LABELS: dict[ContextDimension, str] = {
    ContextDimension.C1_SEMANTIC: "Semantic",
    ContextDimension.C2_ASSET_HIERARCHY: "Asset/Hierarchy",
    ContextDimension.C3_RELATIONAL: "Relational",
    ContextDimension.C4_TEMPORAL: "Temporal",
    ContextDimension.C5_OPERATIONAL: "Operational",
    ContextDimension.C6_PROCEDURAL: "Procedural",
    ContextDimension.C7_HISTORICAL: "Historical",
}

CONTEXT_DIMENSION_DESCRIPTIONS: dict[ContextDimension, str] = {
    ContextDimension.C1_SEMANTIC: (
        "What a canonical id/measurement NAME actually means -- discovering it "
        "via a semantic namespace (UNS) or a standardized object model (i3X)."
    ),
    ContextDimension.C2_ASSET_HIERARCHY: (
        "Which equipment/process-cell/area an item belongs to -- ISA-95 "
        "hierarchy (PART_OF), discoverable via UNS/OPC UA/i3X browsing or "
        "the knowledge graph."
    ),
    ContextDimension.C3_RELATIONAL: (
        "Structural relationships between entities beyond hierarchy -- "
        "MONITORS/ACTUATES (which equipment has which measurement/actuator), "
        "from the knowledge graph or i3X's relationship API."
    ),
    ContextDimension.C4_TEMPORAL: (
        "A value at, or a short range around, a specific point in time -- "
        "get_historical_values/i3x_get_history over a bounded window."
    ),
    ContextDimension.C5_OPERATIONAL: (
        "A live, current operating value -- get_current_value/opcua_read/"
        "read_mqtt/i3x_get_value."
    ),
    ContextDimension.C6_PROCEDURAL: (
        "How the process is actually CONTROLLED -- CONTROLS/HAS_LIMIT/"
        "ASSOCIATED_WITH relationships (M13-A), distinct from C3's purely "
        "structural PART_OF/MONITORS/ACTUATES edges."
    ),
    ContextDimension.C7_HISTORICAL: (
        "Reasoning across a WIDE historical window to notice a gradual/"
        "delayed/statistical pattern (e.g. an early-vs-late trend), as "
        "opposed to C4's single bounded-range lookup -- both use the same "
        "tools, but C7 is reserved for tasks whose ground truth specifically "
        "requires comparing behavior across time, not just retrieving a "
        "past value."
    ),
}

#: Which architectures can supply evidence for each dimension -- a
#: NECESSARY (not sufficient) condition: `BenchmarkTask` requires at
#: least one of these to be in its own `available_architectures` for
#: every dimension it declares. See module docstring.
CONTEXT_DIMENSION_ARCHITECTURES: dict[ContextDimension, frozenset[str]] = {
    ContextDimension.C1_SEMANTIC: frozenset({"uns", "i3x"}),
    ContextDimension.C2_ASSET_HIERARCHY: frozenset({"uns", "opcua", "i3x", "knowledge_graph"}),
    ContextDimension.C3_RELATIONAL: frozenset({"knowledge_graph", "i3x"}),
    ContextDimension.C4_TEMPORAL: frozenset({"historian", "i3x"}),
    ContextDimension.C5_OPERATIONAL: frozenset({"historian", "mqtt", "opcua", "i3x"}),
    ContextDimension.C6_PROCEDURAL: frozenset({"knowledge_graph", "i3x"}),
    ContextDimension.C7_HISTORICAL: frozenset({"historian", "i3x"}),
}


def architectures_supporting(dimension: ContextDimension) -> frozenset[str]:
    return CONTEXT_DIMENSION_ARCHITECTURES[dimension]


def unsupported_dimensions(
    required_context_dimensions: list[ContextDimension],
    available_architectures: list[str],
) -> list[ContextDimension]:
    """
    Which of `required_context_dimensions` have NO architecture in
    `available_architectures` capable of supplying them -- empty means
    every declared dimension is at least architecturally supportable.
    """

    available = set(available_architectures)
    return [
        dimension
        for dimension in required_context_dimensions
        if not (CONTEXT_DIMENSION_ARCHITECTURES[dimension] & available)
    ]
