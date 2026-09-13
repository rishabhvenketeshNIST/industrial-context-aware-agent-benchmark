"""
M10: which architecture actually supplied a given piece of information
during an investigation, and whether the same measurement was acquired
redundantly through more than one architecture.

Distinguishes:

  * discoverability -- the agent learned WHAT exists (a measurement's
    canonical id), via browse_uns / get_entity_relationships /
    i3x_get_objects / i3x_get_related_objects / opcua_browse. No value.
  * acquisition -- the agent retrieved an actual VALUE, via
    get_current_value / get_historical_values / read_mqtt / opcua_read /
    i3x_get_value / i3x_get_history.
  * redundancy -- the same measurement's value acquired via more than one
    distinct architecture within one investigation.

This is a separate, additive analysis from
icab.evaluation.grounded.GroundedInvestigationEvaluator (unchanged) --
wired into icab.experiments.ExperimentRunner as
ExperimentRecord.information_flow.

Cross-architecture identity resolution is architecture-specific, since
each names things its own way:

  * historian/MQTT: the response carries the canonical id directly
    (`measurement_id`/`canonical_id`).
  * OPC UA: only a `node_id` is returned by `opcua_read`; this module
    resolves it by matching against a PRIOR `opcua_browse` response *in
    the same trace* that reported that node_id's `display_name` (which
    `icab.context.opcua.TEPOPCUAServer` sets to the real measurement's own
    published name), then matching that name against
    `icab.tep.measurements.build_real_tep_variables()`. An `opcua_read`
    with no prior matching browse in the trace is NOT resolvable and is
    counted separately (`unresolved_acquisition_count`), not silently
    dropped or guessed at.
  * i3X: `element_id` follows the wrapper's own
    `<connection>!<equipment display name>.<measurement display name>`
    format (see docs/architecture/i3x-private-server.md); the trailing
    segment is matched the same way.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from icab.agent.llm.tools import ARCHITECTURE_TOOL_NAMES
from icab.tep.measurements import build_real_tep_variables
from icab.trace.models import TraceEvent

_DISCOVERY_TOOLS = frozenset(
    {"browse_uns", "get_entity_relationships", "i3x_get_objects", "i3x_get_related_objects", "opcua_browse"}
)
_ACQUISITION_TOOLS = frozenset(
    {
        "get_current_value",
        "get_historical_values",
        "read_mqtt",
        "opcua_read",
        "i3x_get_value",
        "i3x_get_history",
    }
)

_TOOL_TO_ARCHITECTURE: dict[str, str] = {
    tool: architecture
    for architecture, tools in ARCHITECTURE_TOOL_NAMES.items()
    for tool in tools
}


class AcquisitionRecord(BaseModel):
    """One resolved value acquisition: which architecture, for which measurement."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    architecture: str
    tool: str
    step: int


class InformationFlowReport(BaseModel):
    """Discoverability/acquisition/redundancy analysis of one investigation's trace."""

    model_config = ConfigDict(extra="forbid")

    discovered_canonical_ids: list[str]
    acquisitions: list[AcquisitionRecord]

    #: canonical id -> sorted distinct architectures that supplied a value for it.
    architectures_used_per_measurement: dict[str, list[str]]

    #: canonical ids acquired via more than one distinct architecture.
    redundant_measurements: list[str]

    #: total acquisitions beyond the first per measurement, across all measurements.
    redundant_acquisition_count: int

    #: value-bearing tool calls that could not be mapped to a canonical id
    #: (e.g. an opcua_read with no matching prior browse in this trace).
    unresolved_acquisition_count: int

    #: trace events whose result carried an {"error": ...} payload
    #: (a failed/tool-error call the agent recovered from, not a raised
    #: exception -- see LLMInvestigationAgent._execute_tool).
    tool_error_count: int


class InformationFlowAnalyzer:
    """Builds an InformationFlowReport from a recorded investigation trace."""

    def __init__(self) -> None:
        self._name_to_canonical_id = {
            variable.name: variable.canonical_id for variable in build_real_tep_variables()
        }

    def analyze(self, trace: list[TraceEvent]) -> InformationFlowReport:
        discovered: set[str] = set()
        acquisitions: list[AcquisitionRecord] = []
        unresolved = 0
        tool_errors = 0

        # node_id -> display_name, accumulated from opcua_browse events seen
        # so far (in trace order), so a later opcua_read can be resolved.
        node_display_names: dict[str, str] = {}

        for event in trace:
            result = event.result or {}

            if isinstance(result, dict) and "error" in result:
                tool_errors += 1
                continue

            if event.tool in _DISCOVERY_TOOLS:
                discovered.update(self._discovered_ids(event.tool, result, node_display_names))

            if event.tool in _ACQUISITION_TOOLS:
                canonical_ids = self._acquired_ids(event.tool, result, node_display_names)

                if not canonical_ids:
                    unresolved += 1
                    continue

                architecture = _TOOL_TO_ARCHITECTURE.get(event.tool, "unknown")
                for canonical_id in canonical_ids:
                    acquisitions.append(
                        AcquisitionRecord(
                            canonical_id=canonical_id,
                            architecture=architecture,
                            tool=event.tool,
                            step=event.step,
                        )
                    )

        architectures_used: dict[str, set[str]] = {}
        for acquisition in acquisitions:
            architectures_used.setdefault(acquisition.canonical_id, set()).add(
                acquisition.architecture
            )

        redundant_measurements = sorted(
            canonical_id
            for canonical_id, architectures in architectures_used.items()
            if len(architectures) > 1
        )

        redundant_count = sum(
            max(0, len(records) - 1)
            for records in self._group_by_measurement(acquisitions).values()
        )

        return InformationFlowReport(
            discovered_canonical_ids=sorted(discovered),
            acquisitions=acquisitions,
            architectures_used_per_measurement={
                canonical_id: sorted(architectures)
                for canonical_id, architectures in sorted(architectures_used.items())
            },
            redundant_measurements=redundant_measurements,
            redundant_acquisition_count=redundant_count,
            unresolved_acquisition_count=unresolved,
            tool_error_count=tool_errors,
        )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _group_by_measurement(
        acquisitions: list[AcquisitionRecord],
    ) -> dict[str, list[AcquisitionRecord]]:
        groups: dict[str, list[AcquisitionRecord]] = {}
        for acquisition in acquisitions:
            groups.setdefault(acquisition.canonical_id, []).append(acquisition)
        return groups

    def _discovered_ids(
        self,
        tool: str,
        result: dict[str, Any],
        node_display_names: dict[str, str],
    ) -> set[str]:
        ids: set[str] = set()

        if tool == "browse_uns":
            for node in result.get("nodes") or []:
                if node.get("node_type") == "measurement" and node.get("canonical_id"):
                    ids.add(node["canonical_id"])

        elif tool == "get_entity_relationships":
            for relationship in result.get("relationships") or []:
                object_id = relationship.get("object", "")
                if isinstance(object_id, str) and object_id.startswith("urn:icab:measurement:"):
                    ids.add(object_id)

        elif tool == "opcua_browse":
            for node in result.get("nodes") or []:
                node_id = node.get("node_id")
                display_name = node.get("display_name")
                if node_id and display_name:
                    node_display_names[node_id] = display_name
                canonical_id = self._name_to_canonical_id.get(display_name or "")
                if canonical_id:
                    ids.add(canonical_id)

        elif tool in ("i3x_get_objects", "i3x_get_related_objects"):
            objects = result.get("objects") if tool == "i3x_get_objects" else [
                item.get("object", {}) for item in (result.get("related_objects") or [])
            ]
            for obj in objects or []:
                canonical_id = self._canonical_id_from_i3x_element_id(obj.get("element_id"))
                if canonical_id:
                    ids.add(canonical_id)

        return ids

    def _acquired_ids(
        self,
        tool: str,
        result: dict[str, Any],
        node_display_names: dict[str, str],
    ) -> set[str]:
        ids: set[str] = set()

        if tool == "get_current_value":
            observation = result.get("observation")
            if isinstance(observation, dict) and observation.get("measurement_id"):
                ids.add(observation["measurement_id"])

        elif tool == "get_historical_values":
            for observation in result.get("observations") or []:
                if isinstance(observation, dict) and observation.get("measurement_id"):
                    ids.add(observation["measurement_id"])

        elif tool == "read_mqtt":
            message = result.get("message")
            if isinstance(message, dict) and message.get("canonical_id"):
                ids.add(message["canonical_id"])

        elif tool == "opcua_read":
            node_id = result.get("node_id")
            display_name = node_display_names.get(node_id) if node_id else None
            canonical_id = self._name_to_canonical_id.get(display_name or "")
            if canonical_id:
                ids.add(canonical_id)

        elif tool in ("i3x_get_value", "i3x_get_history"):
            canonical_id = self._canonical_id_from_i3x_element_id(result.get("element_id"))
            if canonical_id:
                ids.add(canonical_id)

        return ids

    def _canonical_id_from_i3x_element_id(self, element_id: str | None) -> str | None:
        if not element_id or "!" not in element_id:
            return None

        _connection, _sep, path = element_id.partition("!")

        if "." not in path:
            return None

        _equipment_name, _sep, measurement_name = path.partition(".")
        return self._name_to_canonical_id.get(measurement_name)
