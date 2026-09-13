"""
Deterministic, structured evaluation of an InvestigationResult against a
BenchmarkScenario's ground truth and its recorded trace (M8, hardened M9).

This is additive: `icab.evaluation.investigation.InvestigationEvaluator`
(keyword-substring scoring against the older, flat `InvestigationCase`) is
unchanged, still works, and is still what existing callers get. This
module is the *stronger* evaluator, used wherever a `BenchmarkScenario`
(icab.scenarios, M5) and a recorded trace are available, and is
deliberately NOT an LLM-as-judge: every score here is computed from
structured, deterministic checks against the ground truth, the trace's
recorded tool calls/results, and simple text/number matching -- the same
run scored twice always produces the same report.

Two of the ten evaluation dimensions requested for this milestone are
genuinely hard to check without either a second model call (an
LLM-as-judge, which this milestone deliberately avoids as the *primary*
evaluator) or a full semantic parse of the conclusion text:

  * "structured conclusion correctness" and "causal reasoning" are both
    approximated here by `conclusion_correctness_score` -- whether the
    ground truth's root_cause_disturbance and affected assets are
    *mentioned* in the conclusion text. This checks that the right
    concepts were surfaced, not that the agent's causal argument is
    sound; a correct-sounding conclusion that got there by luck scores the
    same as one that reasoned properly. This is a real limitation, stated
    plainly rather than dressed up as more than it is.

Hardening (M9): running a legacy deterministic baseline against a real
BenchmarkScenario surfaced a genuine false positive -- a run that read the
WRONG (legacy, static-prototype) measurement id still scored
required_evidence_score == 1.0, because the ground truth's required
canonical id happened to appear inside an unrelated
`get_entity_relationships` response (structural relationship data, not a
retrieved value). The root cause was matching evidence by keyword
substring over the *entire* findings blob, which cannot distinguish "the
agent retrieved this measurement's value" from "this id was merely
mentioned somewhere in some other tool's output". Fixed by requiring
required-evidence hits to come from an actual value-bearing retrieval
(get_current_value/get_historical_values/i3x_get_value/i3x_get_history),
the agent's own asserted `evidence`, or its own conclusion text -- never
from scanning raw findings/relationship dumps. See
docs/research/experiment-plan.md for the full incident writeup.

Separately, relationship-based ground truth (`expected_relationships`) is
now generation-scoped: pass `evaluate(..., generation_id=...)` (as
`icab.experiments.ExperimentRunner` does, using the id
`icab.scenarios.runner.ScenarioRunner.prepare()` minted for that
preparation) to require a confirming relationship to have been written by
*this* scenario preparation -- not an unrelated earlier run's leftover
edge in the same shared, persistent knowledge graph. Passing no
generation_id preserves the original (ungated) M8 behavior, so existing
callers/tests are unaffected.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from icab.agent.interface import InvestigationResult, TerminationReason
from icab.scenarios.models import BenchmarkScenario, ScenarioDifficulty
from icab.trace.models import TraceEvent

#: ICAB canonical id shape (see icab.cim.identifiers.CanonicalId). Only
#: evidence sourced from these CIM/canonical-id-based tools is checked
#: against it -- OPC UA node ids, MQTT topics, and i3X element ids have
#: their own, different, equally valid identifier formats.
_CANONICAL_ID_PATTERN = re.compile(r"^urn:icab:[a-z0-9][a-z0-9:_-]*$")
_CANONICAL_ID_SOURCES = frozenset(
    {"get_current_value", "get_historical_values", "get_entity_relationships", "browse_uns"}
)

#: Tool responses that carry an actually-retrieved value for a specific
#: identifier -- as opposed to structural/discovery responses (browse_uns,
#: get_entity_relationships, opcua_browse, i3x_get_objects/
#: get_related_objects) that merely *mention* identifiers without the
#: agent having retrieved their value.
_VALUE_BEARING_TOOLS = frozenset(
    {"get_current_value", "get_historical_values", "i3x_get_value", "i3x_get_history"}
)

_TEMPORAL_TOOLS = frozenset({"get_historical_values", "i3x_get_history"})
_RELATIONSHIP_TOOLS = frozenset({"get_entity_relationships"})

_NUMBER_PATTERN = re.compile(r"-?\d+\.\d+|-?\d{3,}")


class RelationshipCheck(BaseModel):
    """Whether one expected (subject, predicate, object) triple was confirmed in the trace."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    predicate: str
    object: str
    confirmed: bool


class EvaluationReport(BaseModel):
    """Structured, deterministic evaluation of one InvestigationResult."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str

    #: The scenario-preparation generation this report was scoped to (see
    #: module docstring); None if the caller didn't pass one, in which case
    #: relationship confirmation is ungated (original M8 behavior).
    generation_id: str | None = None

    # -- required evidence -------------------------------------------------
    required_evidence_hits: dict[str, bool]
    required_evidence_score: float

    # -- provenance / canonical ids -----------------------------------------
    evidence_has_valid_provenance: bool
    canonical_id_validity: dict[str, bool]
    canonical_id_score: float

    # -- temporal reasoning ---------------------------------------------------
    temporal_evidence_required: bool
    temporal_evidence_acquired: bool

    # -- relationship reasoning -------------------------------------------------
    expected_relationships: list[RelationshipCheck]
    relationship_score: float

    # -- structured conclusion correctness / causal reasoning (heuristic) -------
    root_cause_identified: bool | None
    affected_assets_mentioned: dict[str, bool]
    conclusion_correctness_score: float

    # -- grounding / unsupported claims -----------------------------------------
    unsupported_numeric_claims: list[float]
    grounding_score: float

    # -- acquired vs. consumed context --------------------------------------------
    context_acquired: list[str]
    context_consumed: list[str]

    # -- efficiency / completeness -----------------------------------------------
    tool_call_count: int
    unique_tools_used: list[str]
    terminated_properly: bool
    completeness_score: float


class GroundedInvestigationEvaluator:
    """Scores an InvestigationResult against a BenchmarkScenario's structured ground truth."""

    def evaluate(
        self,
        scenario: BenchmarkScenario,
        result: InvestigationResult,
        trace: list[TraceEvent],
        *,
        generation_id: str | None = None,
    ) -> EvaluationReport:
        ground_truth = scenario.ground_truth
        text = self._collect_text(result).lower()

        retrieved_ids = self._retrieved_value_ids(trace)
        asserted_ids = {evidence.identifier for evidence in result.evidence}

        required_hits = {
            item: (
                item in retrieved_ids
                or item in asserted_ids
                or item.lower() in text
            )
            for item in ground_truth.expected_evidence
        }
        required_score = self._ratio(required_hits)

        canonical_ids = [
            evidence.identifier
            for evidence in result.evidence
            if evidence.source in _CANONICAL_ID_SOURCES
        ]
        id_validity = {
            canonical_id: bool(_CANONICAL_ID_PATTERN.match(canonical_id))
            for canonical_id in canonical_ids
        }
        id_score = self._ratio(id_validity)
        provenance_ok = all(
            bool(evidence.source) and bool(evidence.identifier)
            for evidence in result.evidence
        )

        temporal_required = (
            scenario.difficulty in (ScenarioDifficulty.D3, ScenarioDifficulty.D4)
            or ground_truth.root_cause_disturbance is not None
        )
        temporal_acquired = any(event.tool in _TEMPORAL_TOOLS for event in trace)

        relationship_checks = [
            RelationshipCheck(
                subject=subject,
                predicate=predicate,
                object=object_,
                confirmed=self._relationship_confirmed(
                    subject, predicate, object_, trace, generation_id
                ),
            )
            for subject, predicate, object_ in ground_truth.expected_relationships
        ]
        relationship_score = self._ratio(
            {i: check.confirmed for i, check in enumerate(relationship_checks)}
        )

        root_cause_identified = None
        if ground_truth.root_cause_disturbance is not None:
            root_cause_identified = self._mentions_disturbance(
                ground_truth.root_cause_disturbance, text
            )

        affected_assets = (*ground_truth.affected_measurements, *ground_truth.affected_equipment)
        affected_mentioned = {
            asset: self._slug(asset) in text for asset in affected_assets
        }
        conclusion_correctness_score = self._conclusion_correctness_score(
            root_cause_identified, affected_mentioned
        )

        # Numbers already given in the objective (e.g. a stated trip
        # threshold) are cited context, not a claim the agent needs to have
        # observed through a tool -- caught via a real run during M9
        # validation (a correct answer that cited the objective's own
        # "3000 kPa" threshold was otherwise flagged as unsupported).
        observed_numbers = self._observed_numbers(trace) + [
            float(match) for match in _NUMBER_PATTERN.findall(result.objective)
        ]
        conclusion_numbers = [
            float(match) for match in _NUMBER_PATTERN.findall(result.conclusion)
        ]
        unsupported = [
            number
            for number in conclusion_numbers
            if not self._is_supported(number, observed_numbers)
        ]
        grounding_score = (
            1.0
            if not conclusion_numbers
            else 1.0 - (len(unsupported) / len(conclusion_numbers))
        )

        context_acquired = sorted({item for event in trace for item in event.context_acquired})
        context_consumed = sorted({item for event in trace for item in event.context_consumed})

        terminated_properly = result.termination != TerminationReason.STEP_BUDGET_EXCEEDED
        completeness_components = [required_score, relationship_score, float(terminated_properly)]
        completeness_score = sum(completeness_components) / len(completeness_components)

        return EvaluationReport(
            scenario_id=scenario.scenario_id,
            generation_id=generation_id,
            required_evidence_hits=required_hits,
            required_evidence_score=required_score,
            evidence_has_valid_provenance=provenance_ok,
            canonical_id_validity=id_validity,
            canonical_id_score=id_score,
            temporal_evidence_required=temporal_required,
            temporal_evidence_acquired=temporal_acquired,
            expected_relationships=relationship_checks,
            relationship_score=relationship_score,
            root_cause_identified=root_cause_identified,
            affected_assets_mentioned=affected_mentioned,
            conclusion_correctness_score=conclusion_correctness_score,
            unsupported_numeric_claims=unsupported,
            grounding_score=grounding_score,
            context_acquired=context_acquired,
            context_consumed=context_consumed,
            tool_call_count=len(trace),
            unique_tools_used=sorted({event.tool for event in trace if event.tool}),
            terminated_properly=terminated_properly,
            completeness_score=completeness_score,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _ratio(hits: dict[Any, bool]) -> float:
        # A verification set with nothing in it is vacuously satisfied
        # (there is nothing to be wrong about), not scored as a failure.
        if not hits:
            return 1.0
        return sum(hits.values()) / len(hits)

    @staticmethod
    def _collect_text(result: InvestigationResult) -> str:
        # Deliberately objective + conclusion ONLY -- not `findings`. Raw
        # findings/tool-response dumps are what the agent *saw*, not what
        # it *claimed*; scanning them for required-evidence/causal-mention
        # checks is what let an unrelated get_entity_relationships response
        # satisfy a measurement's evidence requirement (see module
        # docstring). Value-level evidence is checked separately via
        # `_retrieved_value_ids`.
        return f"{result.objective}\n{result.conclusion}"

    @staticmethod
    def _retrieved_value_ids(trace: list[TraceEvent]) -> set[str]:
        """
        Identifiers the agent actually retrieved A VALUE for -- as opposed
        to identifiers merely mentioned in a structural/discovery response
        (relationships, UNS/OPC UA/i3X browsing).
        """

        ids: set[str] = set()

        for event in trace:
            if event.tool not in _VALUE_BEARING_TOOLS:
                continue

            result = event.result or {}

            observation = result.get("observation")
            if isinstance(observation, dict) and observation.get("measurement_id"):
                ids.add(observation["measurement_id"])

            for observation in result.get("observations") or []:
                if isinstance(observation, dict) and observation.get("measurement_id"):
                    ids.add(observation["measurement_id"])

            element_id = result.get("element_id")
            if element_id:
                ids.add(element_id)

        return ids

    @staticmethod
    def _slug(canonical_id: str) -> str:
        return canonical_id.rsplit(":", 1)[-1].replace("_", " ").lower()

    @staticmethod
    def _mentions_disturbance(disturbance: str, text: str) -> bool:
        # Accept either the raw IDV name ("idv_01") or its spelled-out form
        # ("idv 01" / "idv1" / "IDV(1)" style phrasing agents commonly use).
        number = disturbance.rsplit("_", 1)[-1].lstrip("0") or "0"
        candidates = {
            disturbance.lower(),
            disturbance.replace("_", " ").lower(),
            f"idv {number}",
            f"idv{number}",
            f"idv({number})",
        }
        return any(candidate in text for candidate in candidates)

    @staticmethod
    def _conclusion_correctness_score(
        root_cause_identified: bool | None,
        affected_mentioned: dict[str, bool],
    ) -> float:
        components: list[float] = []

        if root_cause_identified is not None:
            components.append(float(root_cause_identified))

        if affected_mentioned:
            components.append(sum(affected_mentioned.values()) / len(affected_mentioned))

        # Nothing to check (e.g. a no-fault D1/D2 scenario) -- vacuously correct.
        return sum(components) / len(components) if components else 1.0

    @staticmethod
    def _relationship_confirmed(
        subject: str,
        predicate: str,
        object_: str,
        trace: list[TraceEvent],
        generation_id: str | None,
    ) -> bool:
        for event in trace:
            if event.tool not in _RELATIONSHIP_TOOLS:
                continue

            relationships = (event.result or {}).get("relationships", [])

            for relationship in relationships:
                if not (
                    relationship.get("subject") == subject
                    and relationship.get("predicate") == predicate
                    and relationship.get("object") == object_
                ):
                    continue

                # Ungated when no generation_id was supplied (original M8
                # behavior); otherwise the confirming relationship must
                # belong to THIS scenario preparation -- not an unrelated
                # earlier run's edge sitting in the same shared,
                # persistent knowledge graph.
                if generation_id is None or relationship.get("generation_id") == generation_id:
                    return True

        return False

    @staticmethod
    def _observed_numbers(trace: list[TraceEvent]) -> list[float]:
        numbers: list[float] = []

        def walk(value: Any) -> None:
            if isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                numbers.append(float(value))
            elif isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        for event in trace:
            walk(event.result)

        return numbers

    @staticmethod
    def _is_supported(number: float, observed: list[float]) -> bool:
        tolerance = max(1.0, abs(number) * 0.02)
        return any(abs(number - value) <= tolerance for value in observed)
