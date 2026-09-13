"""
M12: persists reporting outputs under the existing `results/` hierarchy,
alongside `icab.experiments.storage.ExperimentResultStore` (raw/traces/
evaluations/aggregate/hypotheses) rather than a separate results root --
new subdirectories `results/reports/` (JSON + Markdown) and
`results/figures/` (plots), the latter already anticipated by the
original M9 spec's `results/{raw,traces,evaluations,aggregate,figures}`
structure.
"""

from __future__ import annotations

from pathlib import Path

from .aggregation import AggregationReport
from .hypothesis_report import HypothesisReport


class ReportStore:
    """Reads/writes M12 aggregation/hypothesis reports and figures under a results/ root."""

    def __init__(self, root: str | Path = "results") -> None:
        self.root = Path(root)
        self.reports_dir = self.root / "reports"
        self.figures_dir = self.root / "figures"

    def write_aggregation_report(self, report: AggregationReport, name: str) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{name}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_aggregation_report(self, name: str) -> AggregationReport:
        path = self.reports_dir / f"{name}.json"
        return AggregationReport.model_validate_json(path.read_text(encoding="utf-8"))

    def write_hypothesis_report(self, report: HypothesisReport, name: str) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{name}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_hypothesis_report(self, name: str) -> HypothesisReport:
        path = self.reports_dir / f"{name}.json"
        return HypothesisReport.model_validate_json(path.read_text(encoding="utf-8"))

    def write_markdown(self, text: str, name: str) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def figure_path(self, name: str) -> Path:
        """
        Return (creating the parent dir) the path a figure named `name`
        should be saved to -- callers (`icab.reporting.plotting`) write
        the actual image bytes via `matplotlib`'s own `savefig`.
        """

        self.figures_dir.mkdir(parents=True, exist_ok=True)
        return self.figures_dir / name
