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
from .qa_report import QAReport


class ReportStore:
    """Reads/writes M12 aggregation/hypothesis reports and figures under a results/ root."""

    def __init__(self, root: str | Path = "results") -> None:
        self.root = Path(root)
        self.reports_dir = self.root / "reports"
        self.figures_dir = self.root / "figures"
        #: ICAB question-bank level benchmarks (icab.benchmark.levels):
        #: context-requirement matrix/candidate-MSC/architecture-context/
        #: failure-mode JSON outputs (icab.analysis.reports), and
        #: question/use-case/benchmark-level statistics summaries
        #: (icab.analysis.question_stats) respectively -- additive
        #: sibling directories, same convention as reports_dir/figures_dir.
        self.matrices_dir = self.root / "matrices"
        self.summaries_dir = self.root / "summaries"

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

    def write_qa_report(self, report: QAReport, name: str) -> Path:
        """
        Persists the M13-D researcher-facing question/answer report's
        machine-readable form at `results/reports/<name>-qa.json` --
        suffixed so it never collides with that same name's
        `AggregationReport` JSON (`write_aggregation_report`). The
        human-readable Markdown rendering is written via the existing
        `write_markdown` (also suffixed `-qa` by the caller).
        """

        self.reports_dir.mkdir(parents=True, exist_ok=True)
        path = self.reports_dir / f"{name}-qa.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_qa_report(self, name: str) -> QAReport:
        path = self.reports_dir / f"{name}-qa.json"
        return QAReport.model_validate_json(path.read_text(encoding="utf-8"))

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

    def write_matrix(self, payload: str, name: str) -> Path:
        """Persists one already-serialized (model_dump_json) analysis matrix/table at `<root>/matrices/<name>.json`."""

        self.matrices_dir.mkdir(parents=True, exist_ok=True)
        path = self.matrices_dir / f"{name}.json"
        path.write_text(payload, encoding="utf-8")
        return path

    def write_summary(self, payload: str, name: str) -> Path:
        """Persists one already-serialized question/use-case/benchmark-level statistics summary at `<root>/summaries/<name>.json`."""

        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        path = self.summaries_dir / f"{name}.json"
        path.write_text(payload, encoding="utf-8")
        return path
