"""
CLI tests for scripts/run_level_benchmark.py's user-facing question-
inspection / dry-run / standalone-export additions -- loaded by file path
(scripts/ isn't a package), exercised only through its own module-level
functions (never main()'s gateway/infrastructure preflight), so no real
Postgres/Neo4j/MQTT/Agent-Gateway connection is attempted anywhere here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run_level_benchmark.py"


def _load_module():
    # run_level_benchmark.py does `from run_benchmark import ...` (the
    # pre-existing tep-v1/tep-v2 suite runner it reuses
    # _build_benchmark_runner/_check_gateway_reachable/etc. from) --
    # that only resolves when scripts/ itself is on sys.path, which
    # `uv run python scripts/run_level_benchmark.py` gets for free
    # (CPython adds argv[0]'s directory), but a plain importlib load
    # from inside pytest does not.
    scripts_dir = str(_SCRIPT_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    spec = importlib.util.spec_from_file_location("run_level_benchmark_cli", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli():
    return _load_module()


class TestParserDocumentsEveryNewFlag:
    def test_help_exits_cleanly_and_lists_the_new_flags(self, cli, capsys):
        with pytest.raises(SystemExit) as excinfo:
            cli.build_parser().parse_args(["--help"])
        assert excinfo.value.code == 0

        help_text = capsys.readouterr().out
        for flag in ("--list-questions", "--show-question", "--dry-run", "--resume", "--output", "--no-export"):
            assert flag in help_text

    def test_list_questions_and_show_question_do_not_require_gateway_url_to_parse(self, cli):
        args = cli.build_parser().parse_args(["--level", "equipment", "--list-questions"])
        assert args.list_questions is True
        assert args.gateway_url  # still has its default, just unused by this mode


class TestListQuestions:
    def test_lists_exactly_the_levels_question_bank(self, cli, capsys):
        exit_code = cli._list_questions("equipment", cli.build_parser().parse_args(["--level", "equipment", "--list-questions", "--repetitions", "10"]))
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "Questions: 50" in out
        assert "Planned executions: 500" in out
        assert "Q-d1-qa-current-pressure" in out

    def test_question_ids_filter_narrows_the_listing(self, cli, capsys):
        args = cli.build_parser().parse_args(["--level", "equipment", "--list-questions", "--question-ids", "Q-d1-qa-current-pressure"])
        exit_code = cli._list_questions("equipment", args)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "Questions: 1" in out
        assert "Q-d1-qa-current-pressure" in out


class TestShowQuestion:
    def test_shows_full_existing_metadata_for_a_real_question(self, cli, capsys):
        exit_code = cli._show_question("equipment", "Q-d1-qa-current-pressure")
        out = capsys.readouterr().out

        assert exit_code == 0
        for field in ("question_id:", "isa95_level:", "use_case_id:", "expected_answer_type:", "difficulty:", "tags:", "hypothesized_required_context:", "provenance:", "conclusion:"):
            assert field in out

    def test_unknown_question_id_fails_with_a_clear_error_not_a_traceback(self, cli, capsys):
        exit_code = cli._show_question("equipment", "not-a-real-question")
        err = capsys.readouterr().err

        assert exit_code == 1
        assert "Unknown question_id" in err


class TestDryRun:
    def test_dry_run_makes_no_gateway_call_and_reports_the_exact_plan(self, cli, capsys):
        args = cli.build_parser().parse_args(["--level", "equipment", "--dry-run", "--repetitions", "10"])
        exit_code = cli._dry_run("equipment", args)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "DRY RUN" in out
        assert "Planned instances:   50" in out
        assert "Planned executions:  500" in out

    def test_dry_run_with_a_smaller_repetitions_value_scales_the_plan(self, cli, capsys):
        args = cli.build_parser().parse_args(["--level", "equipment", "--dry-run", "--repetitions", "2", "--question-ids", "Q-d1-qa-current-pressure"])
        exit_code = cli._dry_run("equipment", args)
        out = capsys.readouterr().out

        assert exit_code == 0
        assert "Planned instances:   1" in out
        assert "Planned executions:  2" in out


class TestMainRoutesInspectionFlagsBeforeAnyInfrastructureCheck:
    def test_main_refuses_missing_level_for_inspection_flags_without_touching_infrastructure(self, cli, monkeypatch, capsys):
        # --all + --list-questions parses fine (they're independent argparse
        # flags), but main() must refuse the missing --level itself, and
        # must do so BEFORE any gateway/infrastructure check is reachable --
        # if it reached _check_infrastructure_reachable/_check_gateway_reachable
        # here, this test (no real Postgres/Neo4j/gateway available) would
        # raise instead of returning cleanly.
        monkeypatch.setattr(sys, "argv", ["run_level_benchmark.py", "--all", "--list-questions"])

        exit_code = cli.main()

        assert exit_code == 2
        assert "--level" in capsys.readouterr().err
