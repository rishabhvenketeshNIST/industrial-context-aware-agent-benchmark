"""
ICAB-CR: context representation -- for a use case, how did each
SINGLE-architecture arm actually represent the required context, and
how did that representation's cost/effectiveness compare?

Only single-architecture runs are compared here (a multi-architecture
arm mixes representations, so it is not "one representation" to compare
against another) -- see `ARCHITECTURE_REPRESENTATION_LABELS` for the
documented, real mechanism each architecture actually uses (not
compared unless the underlying information is genuinely the same
dimension; the caller is expected to have scoped `records` to one use
case, whose `required_context`/`candidate_context` already establishes
which dimensions are actually in play).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from icab.experiments.models import ExperimentRecord
from icab.reporting.aggregation import aggregate_records
from icab.reporting.metrics import ALL_METRICS
from icab.usecases import IndustrialUseCase

from ._shared import records_for_use_case

#: What each architecture's tools ACTUALLY return, per
#: icab.agent.llm.tools.ARCHITECTURE_TOOL_NAMES / icab.gateway.tools --
#: a documented, real mechanism, not a marketing label.
ARCHITECTURE_REPRESENTATION_LABELS: dict[str, str] = {
    "historian": "time-series value keyed by canonical measurement id",
    "knowledge_graph": "typed (subject, predicate, object) relationship edge",
    "uns": "hierarchical namespace path with a canonical id leaf",
    "opcua": "OPC UA node reference (browse tree + node id read)",
    "mqtt": "topic-based retained message keyed by a derived topic path",
    "i3x": "standardized i3X object/relationship/value (CESMII spec)",
}


class RepresentationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    architecture: str
    representation: str
    n_runs: int
    effectiveness: dict[str, float | None]
    efficiency: dict[str, float | None]


class RepresentationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_case_id: str
    findings: list[RepresentationFinding]


def analyze_representation(records: list[ExperimentRecord], use_case: IndustrialUseCase) -> RepresentationReport:
    scoped = records_for_use_case(records, use_case.use_case_id)
    single_arch = [record for record in scoped if len(record.config.architectures) == 1]

    if not single_arch:
        return RepresentationReport(use_case_id=use_case.use_case_id, findings=[])

    metric_names = tuple(name for name, _label in ALL_METRICS)
    report = aggregate_records(single_arch, group_by=("architecture",), metrics=metric_names, allow_heterogeneous_controls=True)

    from icab.reporting.metrics import EFFECTIVENESS_METRICS, EFFICIENCY_METRICS

    effectiveness_names = {name for name, _label in EFFECTIVENESS_METRICS}
    efficiency_names = {name for name, _label in EFFICIENCY_METRICS}

    findings = []
    for group in report.groups:
        architecture = group.group_key["architecture"]
        findings.append(
            RepresentationFinding(
                architecture=architecture,
                representation=ARCHITECTURE_REPRESENTATION_LABELS.get(architecture, "(undocumented)"),
                n_runs=group.n_runs,
                effectiveness={name: group.metrics[name].mean for name in metric_names if name in effectiveness_names},
                efficiency={name: group.metrics[name].mean for name in metric_names if name in efficiency_names},
            )
        )

    return RepresentationReport(use_case_id=use_case.use_case_id, findings=findings)
