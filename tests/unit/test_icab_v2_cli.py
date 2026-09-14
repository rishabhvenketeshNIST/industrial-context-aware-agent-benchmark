"""
CLI-parsing/smoke tests for scripts/icab_v2_cli.py -- loaded by file path
(scripts/ isn't a package). The `list-*`/`analyze-*`/`generate-profiles`
subcommands need no external infrastructure (they read the real,
checked-in configs/usecases/ + configs/benchmark/ registries, and, for
analyze-*/generate-profiles, an empty/nonexistent results/ directory is
a legitimate "no evidence yet" input, not an error) -- `validate-architectures`
needs the real Docker stack and is exercised by
tests/integration/test_architecture_connectivity.py instead, not here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "icab_v2_cli.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("icab_v2_cli", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli():
    return _load_module()


class TestListCommands:
    def test_list_isa95_levels_runs_and_prints_every_level(self, cli, capsys):
        args = cli.build_parser().parse_args(["list-isa95-levels"])
        exit_code = args.func(args)

        assert exit_code == 0
        out = capsys.readouterr().out
        for level in ("enterprise", "site", "area", "work_center", "process_cell", "equipment"):
            assert level in out

    def test_list_use_cases_runs(self, cli, capsys):
        args = cli.build_parser().parse_args(["list-use-cases"])
        exit_code = args.func(args)

        assert exit_code == 0
        assert "eq-current-value-interpretation" in capsys.readouterr().out

    def test_list_use_cases_filters_by_level(self, cli, capsys):
        args = cli.build_parser().parse_args(["list-use-cases", "--level", "area"])
        args.func(args)

        out = capsys.readouterr().out
        assert "area-site-membership-identification" in out
        assert "eq-current-value-interpretation" not in out

    def test_list_context_dimensions_prints_all_seven(self, cli, capsys):
        args = cli.build_parser().parse_args(["list-context-dimensions"])
        args.func(args)

        out = capsys.readouterr().out
        for dimension in ("C1", "C2", "C3", "C4", "C5", "C6", "C7"):
            assert dimension in out

    def test_list_context_combinations_default_shows_all_127(self, cli, capsys):
        args = cli.build_parser().parse_args(["list-context-combinations"])
        args.func(args)

        assert "127 combination(s) shown" in capsys.readouterr().out

    def test_list_context_combinations_cardinality_filter(self, cli, capsys):
        args = cli.build_parser().parse_args(["list-context-combinations", "--cardinality", "1"])
        args.func(args)

        assert "7 combination(s) shown" in capsys.readouterr().out


class TestValidateFaults:
    def test_runs_against_the_real_checked_in_fault_catalog(self, cli, capsys):
        args = cli.build_parser().parse_args(["validate-faults"])
        exit_code = args.func(args)

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "empirically_verified" in out


class TestAnalyzeCommandsWithNoEvidence:
    """
    An empty/nonexistent results directory is a legitimate "nothing
    tested yet" input for analyze-*, not an error -- these commands must
    still produce a well-formed (empty) report rather than crashing.
    """

    @pytest.mark.parametrize(
        "subcommand",
        ["analyze-necessity", "analyze-sufficiency", "analyze-composition", "analyze-representation", "analyze-architecture"],
    )
    def test_runs_cleanly_with_no_persisted_results(self, cli, capsys, tmp_path, subcommand):
        args = cli.build_parser().parse_args(
            [subcommand, "--use-case", "eq-current-value-interpretation", "--results-root", str(tmp_path)]
        )
        exit_code = args.func(args)

        assert exit_code == 0
        capsys.readouterr()  # must not raise while producing output

    def test_unknown_use_case_id_fails_clearly(self, cli, tmp_path):
        # main() catches KeyError from an unknown use case and returns 2
        # -- exercised via sys.argv the same way a real invocation would be.
        import sys as _sys

        old_argv = _sys.argv
        try:
            _sys.argv = ["icab_v2_cli.py", "analyze-necessity", "--use-case", "not-a-real-use-case", "--results-root", str(tmp_path)]
            exit_code = cli.main()
        finally:
            _sys.argv = old_argv

        assert exit_code == 2


class TestGenerateProfiles:
    def test_writes_a_json_file_when_out_is_given(self, cli, tmp_path):
        output_path = tmp_path / "profiles.json"
        args = cli.build_parser().parse_args(
            ["generate-profiles", "--results-root", str(tmp_path / "results"), "--out", str(output_path)]
        )

        exit_code = args.func(args)

        assert exit_code == 0
        assert output_path.exists()

    def test_no_evidence_produces_an_empty_but_valid_json_object(self, cli, tmp_path):
        output_path = tmp_path / "profiles.json"
        args = cli.build_parser().parse_args(
            ["generate-profiles", "--results-root", str(tmp_path / "results"), "--out", str(output_path)]
        )
        args.func(args)

        import json

        content = json.loads(output_path.read_text(encoding="utf-8"))
        assert content == {}
