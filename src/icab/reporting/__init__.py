"""
M12: turns persisted M9-M11 experiment artifacts (results/{raw,traces,
evaluations}/) into reproducible research outputs -- grouped aggregation
across experimental dimensions, richer hypothesis reports, and plots.

This package only READS already-persisted `ExperimentRecord`s (via
`icab.experiments.ExperimentResultStore`) and writes derived reports/
figures; it never runs the simulator, the gateway, or an LLM. Given the
same persisted input records, every function here is deterministic.
"""

from .aggregation import (
    AggregationReport,
    GroupSummary,
    aggregate_records,
    list_dimensions,
)
from .hypothesis_report import HypothesisReport, build_hypothesis_report
from .markdown import render_aggregation_markdown, render_hypothesis_markdown
from .metrics import ALL_METRICS, EFFECTIVENESS_METRICS, EFFICIENCY_METRICS
from .qa_report import CorrectAnswer, QAReport, QAReportEntry, build_qa_report, render_qa_report_markdown
from .stats import SummaryStats, summarize
from .store import ReportStore

__all__ = [
    "ALL_METRICS",
    "EFFECTIVENESS_METRICS",
    "EFFICIENCY_METRICS",
    "AggregationReport",
    "CorrectAnswer",
    "GroupSummary",
    "HypothesisReport",
    "QAReport",
    "QAReportEntry",
    "ReportStore",
    "SummaryStats",
    "aggregate_records",
    "build_hypothesis_report",
    "build_qa_report",
    "list_dimensions",
    "render_aggregation_markdown",
    "render_hypothesis_markdown",
    "render_qa_report_markdown",
    "summarize",
]
