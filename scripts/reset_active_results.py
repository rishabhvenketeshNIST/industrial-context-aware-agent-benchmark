"""
Safe reset of ICAB's ACTIVE, generated results -- ARCHIVES (never
deletes) generated content into a timestamped `results/_archive/
<timestamp>/`, then (re)creates the clean, level-separated
`results/{enterprise,site,area,work_center,process_cell,equipment}/`
skeleton (per `icab.benchmark.levels.LEVEL_BENCHMARKS`) so a fresh
question-bank benchmark campaign starts clean and cannot be contaminated
by pre-existing results (from any prior milestone, mixed v1/v2 results,
or a prior 50-question campaign).

Handles BOTH:
  * the OLD flat `results/{raw,traces,evaluations,aggregate,reports,
    figures,hypotheses,prototype}/` layout (pre-ICAB-v3), and
  * the CURRENT level-scoped `results/<level>/{raw,traces,evaluations,
    aggregate,hypotheses,reports,matrices,summaries}/` + `manifest.json`
    layout -- so this script is genuinely reusable EVERY time a fresh
    campaign is about to start, not a one-time flat-to-level migration.

Archive destinations preserve their full path relative to the results/
root (e.g. `results/_archive/<ts>/equipment/raw/...`), so two levels'
same-named subdirectories (both have a `raw/`) never collide.

NEVER touches (hard-coded refusal, not just "doesn't happen to"):
  * src/, tests/, docs/, configs/ (source code, tests, documentation,
    benchmark/question-bank/scenario/task DEFINITIONS)
  * results/architecture_health.json (the one exception to the
    generated-results-are-gitignored policy -- see
    docs/benchmark/specification-v2.md)
  * any existing results/_archive/ (never re-archived/overwritten)
  * anything under configs/benchmark/tasks/ or configs/benchmark/scenarios/
    that tep-v1 depends on (this script touches results/ ONLY, never configs/)

Refuses to run at all without `--force` (or, with no `--force`, prints
exactly what it WOULD do and exits 0 without touching anything -- a
dry run is the default, not an accident).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

RESULTS_ROOT = Path("results")

#: The OLD flat layout's generated subdirectories -- exactly the ones
#: `.gitignore` already excludes from version control (see
#: docs/benchmark/specification-v2.md's "results/ policy").
OLD_GENERATED_SUBDIRS = ("raw", "traces", "evaluations", "aggregate", "reports", "figures", "hypotheses", "prototype")

#: The CURRENT level-scoped layout's generated subdirectories --
#: everything `icab.benchmark.question_runner`/`icab.reporting.ReportStore`
#: write to under `results/<level>/`.
LEVEL_GENERATED_SUBDIRS = ("raw", "traces", "evaluations", "aggregate", "hypotheses", "reports", "matrices", "summaries")

#: Never touched, no matter what -- explicit, not merely "outside the
#: glob we happen to use."
PROTECTED_PATHS = (
    Path("src"),
    Path("tests"),
    Path("docs"),
    Path("configs"),
    Path("results/architecture_health.json"),
)

from icab.benchmark.levels import LEVEL_BENCHMARKS  # noqa: E402 -- after argparse-only stdlib imports, before use


def _new_level_skeleton_dirs(level_root: Path) -> list[Path]:
    return [
        level_root / "raw",
        level_root / "traces",
        level_root / "evaluations",
        level_root / "aggregate",
        level_root / "hypotheses",
        level_root / "reports",
        level_root / "matrices",
        level_root / "summaries",
    ]


def _archive_timestamp() -> str:
    """Microsecond precision -- plain second-resolution timestamps can collide across rapid successive calls (e.g. tests, or two resets run back to back)."""

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def _has_generated_content(directory: Path) -> bool:
    """True if `directory` holds anything besides `.gitkeep` (or doesn't exist as a plain, empty dir)."""

    if not directory.exists():
        return False
    return any(entry.name != ".gitkeep" for entry in directory.iterdir())


def plan(results_root: Path = RESULTS_ROOT) -> dict:
    archive_dir = results_root / "_archive" / _archive_timestamp()

    to_archive: list[Path] = [
        results_root / subdir
        for subdir in OLD_GENERATED_SUBDIRS
        if (results_root / subdir).exists() and any((results_root / subdir).iterdir())
    ]

    #: Built from the PASSED-IN results_root, not each definition's own
    #: (production-default) `results_root` field directly -- so this
    #: plan is genuinely parameterizable (e.g. by tests, against a
    #: tmp_path) rather than always writing to the real results/ tree
    #: regardless of what was asked for.
    level_roots = [results_root / level.isa95_level.value for level in LEVEL_BENCHMARKS.values()]

    for level_root in level_roots:
        for subdir in LEVEL_GENERATED_SUBDIRS:
            path = level_root / subdir
            if _has_generated_content(path):
                to_archive.append(path)
        manifest = level_root / "manifest.json"
        if manifest.exists():
            to_archive.append(manifest)

    to_create = [d for level_root in level_roots for d in _new_level_skeleton_dirs(level_root)]

    return {"archive_dir": archive_dir, "to_archive": to_archive, "to_create": to_create}


def _refuse_if_protected(paths: list[Path]) -> None:
    for path in paths:
        for protected in PROTECTED_PATHS:
            try:
                path.resolve().relative_to(protected.resolve())
            except ValueError:
                continue
            raise SystemExit(f"error: refusing to touch protected path {path} (under {protected})")


def execute(results_root: Path = RESULTS_ROOT) -> dict:
    reset_plan = plan(results_root)
    _refuse_if_protected(reset_plan["to_archive"])
    _refuse_if_protected(reset_plan["to_create"])

    archive_dir = reset_plan["archive_dir"]
    if reset_plan["to_archive"]:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for source in reset_plan["to_archive"]:
            # Preserve the FULL relative path under the archive -- two
            # different levels both have a "raw/" subdirectory, so
            # archiving by bare name alone would silently collide/
            # overwrite one level's archived data with another's.
            destination = archive_dir / source.relative_to(results_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))

            if source.suffix:  # a file (e.g. manifest.json) -- archived, not recreated; a fresh level simply has none yet.
                continue
            source.mkdir(parents=True, exist_ok=True)
            (source / ".gitkeep").touch()

    for target in reset_plan["to_create"]:
        target.mkdir(parents=True, exist_ok=True)
        (target / ".gitkeep").touch()

    return reset_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Actually perform the archive + skeleton creation. Without this, only a dry-run plan is printed.")
    parser.add_argument("--results-root", default=str(RESULTS_ROOT), help="Root results/ directory. Default: 'results'.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results_root = Path(args.results_root)

    if not args.force:
        reset_plan = plan(results_root)
        print("DRY RUN (pass --force to actually perform this):")
        print(f"  archive destination: {reset_plan['archive_dir']}")
        print("  paths to archive (non-empty, both old flat and current level-scoped layouts):")
        for path in reset_plan["to_archive"]:
            print(f"    - {path}")
        print("  new level-scoped skeleton directories to create:")
        for path in reset_plan["to_create"]:
            print(f"    - {path}")
        print("\nNothing was changed. Protected (never touched): src/, tests/, docs/, configs/, results/architecture_health.json.")
        return 0

    reset_plan = execute(results_root)
    print(f"Archived {len(reset_plan['to_archive'])} old result director(ies) to {reset_plan['archive_dir']}")
    print(f"Created {len(reset_plan['to_create'])} new level-scoped skeleton director(ies) under {results_root}/<level>/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
