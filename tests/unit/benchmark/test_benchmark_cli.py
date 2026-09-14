"""
CLI-parsing tests for scripts/run_benchmark.py -- loaded by file path
(scripts/ isn't a package) and exercised only through `build_parser()`/
`build_benchmark_config()`, never `main()` itself, so no real
historian/knowledge-graph/MQTT connection is attempted.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run_benchmark.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_benchmark_cli", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli():
    return _load_module()


def _parse(cli, argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return cli.build_benchmark_config(args)


class TestRequiredArguments:
    def test_suite_is_required(self, cli):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args([])

    def test_minimal_valid_invocation(self, cli):
        config = _parse(cli, ["--suite", "tep-v1"])
        assert config.suite == "tep-v1"
        assert config.agent == "llm"  # default
        assert config.architectures == "all"  # default
        assert config.repetitions == 1


class TestFullExampleCommand:
    def test_the_documented_full_benchmark_command(self, cli):
        config = _parse(
            cli,
            [
                "--suite", "tep-v1",
                "--agent", "llm",
                "--architectures", "all",
                "--seeds", "1,2,3,4,5",
            ],
        )
        assert config.suite == "tep-v1"
        assert config.agent == "llm"
        assert config.architectures == "all"
        assert config.seeds == [1, 2, 3, 4, 5]

    def test_the_documented_smoke_test_command(self, cli):
        config = _parse(
            cli,
            [
                "--suite", "tep-v1",
                "--split", "development",
                "--task", "d1-qa-current-pressure",
                "--agent", "baseline",
                "--architectures", "historian",
                "--seeds", "1",
            ],
        )
        assert config.suite == "tep-v1"
        assert config.split == "development"
        assert config.task_id == "d1-qa-current-pressure"
        assert config.agent == "baseline"
        assert config.architectures == "historian"
        assert config.seeds == [1]


class TestSeedParsing:
    def test_no_seeds_flag_leaves_seeds_none(self, cli):
        config = _parse(cli, ["--suite", "tep-v1"])
        assert config.seeds is None

    def test_seeds_are_parsed_as_integers(self, cli):
        config = _parse(cli, ["--suite", "tep-v1", "--seeds", "10, 20 ,30"])
        assert config.seeds == [10, 20, 30]


class TestBudgetFlags:
    def test_all_budget_flags_are_parsed(self, cli):
        config = _parse(
            cli,
            [
                "--suite", "tep-v1",
                "--max-steps", "10",
                "--max-tool-calls", "5",
                "--max-context-tokens", "4000",
                "--max-wall-time", "30.5",
                "--temperature", "0.2",
                "--llm-model", "test-model",
            ],
        )
        assert config.max_steps == 10
        assert config.max_tool_calls == 5
        assert config.max_context_tokens == 4000
        assert config.max_wall_time_seconds == 30.5
        assert config.llm_temperature == 0.2
        assert config.llm_model == "test-model"


class TestNameOverride:
    def test_name_flag_overrides_auto_generated_id(self, cli):
        config = _parse(cli, ["--suite", "tep-v1", "--name", "my-benchmark-run"])
        assert config.name == "my-benchmark-run"
