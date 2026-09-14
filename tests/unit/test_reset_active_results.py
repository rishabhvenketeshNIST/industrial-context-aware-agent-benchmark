"""
Unit tests for `scripts/reset_active_results.py` -- loaded by file path
(scripts/ isn't a package). Exercises `plan()`/`execute()`/protected-path
refusal against a real `tmp_path`, never against the repo's own
`results/`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reset_active_results.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reset_active_results", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reset_module():
    return _load_module()


def _make_old_layout(root: Path) -> None:
    for subdir in ("raw", "traces", "evaluations", "aggregate", "reports", "figures"):
        (root / subdir).mkdir(parents=True, exist_ok=True)
        (root / subdir / "some-record.json").write_text("{}", encoding="utf-8")
    (root / "hypotheses").mkdir(parents=True, exist_ok=True)  # left empty
    (root / "architecture_health.json").write_text("{}", encoding="utf-8")


class TestPlan:
    def test_dry_run_plan_identifies_non_empty_old_dirs_only(self, tmp_path, reset_module):
        _make_old_layout(tmp_path)

        result = reset_module.plan(tmp_path)

        archived_names = {p.name for p in result["to_archive"]}
        assert archived_names == {"raw", "traces", "evaluations", "aggregate", "reports", "figures"}
        assert not any(p.name == "hypotheses" for p in result["to_archive"])  # empty -- nothing to archive

    def test_plan_never_mutates_anything(self, tmp_path, reset_module):
        _make_old_layout(tmp_path)

        reset_module.plan(tmp_path)

        assert (tmp_path / "raw" / "some-record.json").exists()  # untouched
        assert not (tmp_path / "_archive").exists()

    def test_plan_lists_all_six_level_skeletons(self, tmp_path, reset_module):
        result = reset_module.plan(tmp_path)

        levels = {"enterprise", "site", "area", "work_center", "process_cell", "equipment"}
        created_levels = {p.parts[-2] for p in result["to_create"]}
        assert created_levels == levels


class TestExecute:
    def test_archives_old_content_and_creates_new_skeleton(self, tmp_path, reset_module):
        _make_old_layout(tmp_path)

        result = reset_module.execute(tmp_path)

        # Old content moved into the archive, not deleted.
        archived = result["archive_dir"]
        assert (archived / "raw" / "some-record.json").exists()
        # The old location is recreated empty (with a .gitkeep), not left missing.
        assert (tmp_path / "raw").exists()
        assert (tmp_path / "raw" / "some-record.json").exists() is False
        assert (tmp_path / "raw" / ".gitkeep").exists()

        # New level-scoped skeleton exists.
        for level in ("enterprise", "site", "area", "work_center", "process_cell", "equipment"):
            assert (tmp_path / level / "raw").exists()
            assert (tmp_path / level / "matrices").exists()
            assert (tmp_path / level / "summaries").exists()

    def test_architecture_health_json_is_never_touched(self, tmp_path, reset_module):
        _make_old_layout(tmp_path)

        reset_module.execute(tmp_path)

        assert (tmp_path / "architecture_health.json").exists()  # still exactly where it was
        assert (tmp_path / "architecture_health.json").read_text(encoding="utf-8") == "{}"

    def test_running_twice_is_safe_and_creates_a_second_archive(self, tmp_path, reset_module):
        _make_old_layout(tmp_path)
        first = reset_module.execute(tmp_path)

        # Put something new in the (now-empty) old layout, then reset again.
        (tmp_path / "raw" / "another-record.json").write_text("{}", encoding="utf-8")
        second = reset_module.execute(tmp_path)

        assert first["archive_dir"] != second["archive_dir"]
        assert (second["archive_dir"] / "raw" / "another-record.json").exists()
        assert (first["archive_dir"] / "raw" / "some-record.json").exists()  # first archive still intact


class TestProtectedPaths:
    def test_refuses_to_touch_src_tests_docs_configs(self, tmp_path, reset_module):
        # Simulate a hypothetical future bug: a "to_archive" or "to_create"
        # path pointing inside a protected directory must be refused, not
        # silently allowed.
        protected_candidates = [
            Path("src") / "icab" / "something",
            Path("tests") / "unit" / "something",
            Path("docs") / "something",
            Path("configs") / "something",
        ]
        for candidate in protected_candidates:
            with pytest.raises(SystemExit):
                reset_module._refuse_if_protected([candidate])

    def test_a_normal_results_path_is_not_refused(self, reset_module):
        reset_module._refuse_if_protected([Path("results") / "equipment" / "raw"])  # does not raise
