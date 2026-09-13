"""
Named architecture-combination presets (M10).

Architecture combinations are a first-class experimental variable: rather
than every experiment re-typing an ad hoc `architectures` list, these
presets are explicit, documented tool-availability configurations an
experiment can reference by key. The underlying enforcement mechanism is
unchanged from M9 -- `icab.agent.llm.tools.tools_for_architectures` still
restricts the LLM agent to exactly these architectures' tools; a
combination is a *label* over that same list, not a new enforcement path
(``ExperimentConfig.architecture_combination_key`` records which preset a
run used, purely for aggregate labeling).

These eight are deliberately not claimed to be the scientifically optimal
set -- they are documented starting points chosen to cover distinct
research questions:

- a single-architecture floor (historian alone)
- a discovery+streaming pair with no query/relational layer (UNS+MQTT)
- three "one value channel + one other axis" pairs (OPC UA/i3X/KG each
  with historian) to compare how each *non-historian* architecture's own
  access pattern combines with a time-series channel
- a discovery+query+relational triple (UNS+historian+KG)
- a "two independent value channels + discovery, no relational layer"
  triple (MQTT+UNS+historian) -- chosen specifically to produce
  measurable redundant acquisition (the same measurement reachable via
  two separate value channels) without a KG to reason about why
- the full architecture set, deliberately included to demonstrate that
  "more architectures" is not simply "strictly better" once redundant
  acquisition and tool-call overhead are counted (see
  icab.evaluation.information_flow)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchitectureCombination:
    """One named, documented architecture-availability preset."""

    key: str
    label: str
    architectures: tuple[str, ...]
    rationale: str


ARCHITECTURE_COMBINATIONS: tuple[ArchitectureCombination, ...] = (
    ArchitectureCombination(
        key="historian_only",
        label="Historian",
        architectures=("historian",),
        rationale=(
            "Single-architecture floor: raw time-series access only, no "
            "discovery, no relationships, no streaming. The baseline every "
            "other combination is compared against."
        ),
    ),
    ArchitectureCombination(
        key="uns_mqtt",
        label="UNS + MQTT",
        architectures=("uns", "mqtt"),
        rationale=(
            "Discovery (UNS namespace browsing) plus streaming/pub-sub value "
            "access (MQTT retained values), with NO query-style historian/KG "
            "access at all -- tests whether an agent can complete an "
            "investigation through discovery+streaming architectures alone."
        ),
    ),
    ArchitectureCombination(
        key="opcua_historian",
        label="OPC UA + Historian",
        architectures=("opcua", "historian"),
        rationale=(
            "Node-based live browsing (OPC UA) combined with time-series "
            "query (historian) -- no relational/semantic layer at all."
        ),
    ),
    ArchitectureCombination(
        key="i3x_historian",
        label="i3X + Historian",
        architectures=("i3x", "historian"),
        rationale=(
            "Standardized object/relationship discovery (i3X) combined with "
            "historian time series -- tests whether i3X's built-in "
            "relationships substitute for a dedicated knowledge graph."
        ),
    ),
    ArchitectureCombination(
        key="kg_historian",
        label="Knowledge Graph + Historian",
        architectures=("knowledge_graph", "historian"),
        rationale=(
            "Explicit relational reasoning (KG) combined with time-series "
            "query (historian) -- the pairing the D2/D3 scenarios were "
            "designed around."
        ),
    ),
    ArchitectureCombination(
        key="uns_historian_kg",
        label="UNS + Historian + Knowledge Graph",
        architectures=("uns", "historian", "knowledge_graph"),
        rationale=(
            "Adds discovery (UNS) on top of the historian+KG pairing -- "
            "tests whether the agent can find measurement ids itself "
            "instead of them being implied by the objective."
        ),
    ),
    ArchitectureCombination(
        key="mqtt_uns_historian",
        label="MQTT + UNS + Historian",
        architectures=("mqtt", "uns", "historian"),
        rationale=(
            "Discovery (UNS) plus TWO independent value-access channels "
            "(MQTT streaming, historian query) with NO relational layer -- "
            "chosen specifically to produce measurable redundant "
            "acquisition (the same measurement reachable via two separate "
            "value channels) without a KG available to explain why."
        ),
    ),
    ArchitectureCombination(
        key="full",
        label="Full contextual architecture",
        architectures=("mqtt", "uns", "opcua", "i3x", "historian", "knowledge_graph"),
        rationale=(
            "Every architecture available -- the upper bound for "
            "comparison. Deliberately included to demonstrate that 'more "
            "architectures' is not simply 'strictly better' once redundant "
            "acquisition and tool-call overhead are counted (see "
            "icab.evaluation.information_flow.InformationFlowAnalyzer)."
        ),
    ),
)

_BY_KEY: dict[str, ArchitectureCombination] = {
    combination.key: combination for combination in ARCHITECTURE_COMBINATIONS
}


def get_combination(key: str) -> ArchitectureCombination:
    """Return a named combination by key, or raise KeyError with valid keys listed."""

    try:
        return _BY_KEY[key]
    except KeyError:
        raise KeyError(
            f"Unknown architecture combination: {key!r}. "
            f"Valid keys: {sorted(_BY_KEY)}"
        ) from None


def list_combination_keys() -> list[str]:
    return sorted(_BY_KEY)
