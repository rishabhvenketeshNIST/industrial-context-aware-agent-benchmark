"""
The user-facing, standalone benchmark execution/results export layer.

Sits ABOVE the existing execution path
(`icab.benchmark.question_runner.QuestionBenchmarkRunner`, which itself
reuses `icab.benchmark._execution`) -- this package adds no new
execution mechanism. It only reshapes already-persisted
`ExperimentRecord`s (+ traces, `Question`, `BenchmarkTask`) into a
standalone, ICAB-import-free dataset under `benchmark_exports/`, kept
entirely separate from ICAB's own internal `results/` store.

    build_canonical_record   ExperimentRecord -> CanonicalExecutionRecord
    CampaignExportWriter     writes the full benchmark_exports/... tree
    build_campaign_metrics   metrics.json content
    validate_export          standalone integrity checks over a written export
"""

from __future__ import annotations

from .build import build_canonical_record
from .metrics import build_campaign_metrics
from .schema import EXPORT_SCHEMA_VERSION, CanonicalExecutionRecord
from .validation import ExportValidationReport, validate_export
from .writer import CampaignExportWriter

__all__ = [
    "EXPORT_SCHEMA_VERSION",
    "CampaignExportWriter",
    "CanonicalExecutionRecord",
    "ExportValidationReport",
    "build_campaign_metrics",
    "build_canonical_record",
    "validate_export",
]
