"""
M12's curated "core metrics" registry -- every metric named in the M12
build direction's "Core metrics" list, mapped to the metric-name strings
`icab.experiments.hypotheses.metric_value` already knows how to resolve
from an `ExperimentRecord`, deliberately kept as TWO separate groups
(effectiveness vs efficiency) rather than collapsed into one score --
per that direction: "Keep effectiveness and efficiency metrics distinct
rather than collapsing everything into one arbitrary score."

Each entry is `(metric_name, label)`; `metric_name` is what
`metric_value`/`aggregate_records` take, `label` is what a report/plot
shows a human.
"""

from __future__ import annotations

from icab.experiments.hypotheses import metric_value

__all__ = ["ALL_METRICS", "EFFECTIVENESS_METRICS", "EFFICIENCY_METRICS", "metric_value"]

#: Quality of the investigation itself -- "how good was the answer and
#: its grounding," independent of how much it cost to get there.
EFFECTIVENESS_METRICS: tuple[tuple[str, str], ...] = (
    ("conclusion_correctness_score", "Investigation correctness"),
    ("required_evidence_score", "Evidence score"),
    ("grounding_score", "Grounded evidence"),
    ("completeness_score", "Context completeness"),
    ("relationship_score", "Relationship/causal reasoning"),
    ("temporal_reasoning_score", "Temporal reasoning"),
    ("unsupported_numeric_claims_count", "Unsupported claims (lower is better)"),
)

#: Cost of reaching that investigation -- "how much work/context/latency
#: did it take," independent of whether the answer was any good.
EFFICIENCY_METRICS: tuple[tuple[str, str], ...] = (
    ("tool_call_count", "Tool calls"),
    ("context_acquired_count", "Context acquired"),
    ("context_consumed_count", "Context consumed"),
    ("information_flow.redundant_acquisition_count", "Redundant acquisition"),
    ("information_flow.tool_error_count", "Tool errors"),
    ("total_latency_ms", "Latency (ms)"),
    ("total_tokens", "Token usage"),
)

ALL_METRICS: tuple[tuple[str, str], ...] = EFFECTIVENESS_METRICS + EFFICIENCY_METRICS
