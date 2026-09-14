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
from unittest.mock import Mock

import httpx
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

    def test_help_exits_cleanly_and_documents_every_flag(self, cli, capsys):
        # --help must work without any gateway/infrastructure -- argparse
        # short-circuits before main()'s own preflight checks ever run.
        with pytest.raises(SystemExit) as excinfo:
            cli.build_parser().parse_args(["--help"])
        assert excinfo.value.code == 0

        help_text = capsys.readouterr().out
        for flag in (
            "--suite", "--split", "--task", "--scenario", "--agent",
            "--architectures", "--seeds", "--repetitions", "--llm-model",
            "--temperature", "--max-steps", "--max-tool-calls",
            "--max-context-tokens", "--max-wall-time", "--name", "--force",
            "--gateway-url", "--results-root",
        ):
            assert flag in help_text

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

    def test_force_defaults_to_false(self, cli):
        config = _parse(cli, ["--suite", "tep-v1", "--name", "my-benchmark-run"])
        assert config.force is False

    def test_force_flag_is_parsed(self, cli):
        config = _parse(cli, ["--suite", "tep-v1", "--name", "my-benchmark-run", "--force"])
        assert config.force is True


class TestConfigurationErrorsExitCleanly:
    """
    A bad --repetitions/budget value must fail as ONE clear message
    (pydantic's ValidationError, caught in main()), never a bare Python
    traceback as the only explanation.
    """

    def test_invalid_repetitions_raises_a_validation_error(self, cli):
        args = cli.build_parser().parse_args(["--suite", "tep-v1", "--repetitions", "0"])
        with pytest.raises(Exception, match="repetitions"):
            cli.build_benchmark_config(args)

    def test_malformed_seeds_exits_with_an_actionable_message(self, cli):
        args = cli.build_parser().parse_args(["--suite", "tep-v1", "--seeds", "abc"])
        with pytest.raises(SystemExit, match="not a comma-separated list of integers"):
            cli.build_benchmark_config(args)


class TestGatewayPreflightCheck:
    """
    Diagnoses the actual failure mode a real run hit: the Agent Gateway
    wasn't running, so every run's first tool call raised a raw
    `ConnectError` only AFTER a full scenario preparation had already
    completed. `_check_gateway_reachable` must catch this up front, with
    an actionable message, before any (expensive) run starts.
    """

    def test_unreachable_gateway_exits_with_an_actionable_message(self, cli, monkeypatch):
        def fake_get(url, **kwargs):
            raise httpx.ConnectError("Connection refused", request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)

        with pytest.raises(SystemExit) as excinfo:
            cli._check_gateway_reachable("http://localhost:8000")

        message = str(excinfo.value)
        assert "not reachable" in message
        assert "http://localhost:8000" in message
        assert "uvicorn icab.gateway.app:app" in message  # actionable fix, not just a raw traceback

    def test_reachable_gateway_returns_normally(self, cli, monkeypatch):
        def fake_get(url, **kwargs):
            return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)

        cli._check_gateway_reachable("http://localhost:8000")  # must not raise

    def test_gateway_returning_an_error_status_also_fails_fast(self, cli, monkeypatch):
        def fake_get(url, **kwargs):
            return httpx.Response(503, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", fake_get)

        with pytest.raises(SystemExit, match="not reachable"):
            cli._check_gateway_reachable("http://localhost:8000")


class _FakeSettings:
    database_url = "postgresql://icab:icab@localhost:5432/icab"
    neo4j_uri = "bolt://localhost:7687"
    neo4j_username = "neo4j"
    neo4j_password = "icabpassword"
    mqtt_host = "localhost"
    mqtt_port = 1883


class TestInfrastructurePreflightCheck:
    """
    Mirrors TestGatewayPreflightCheck's rationale, but for PostgreSQL/
    Neo4j/MQTT -- all three connect lazily, so an unreachable service
    would otherwise only surface deep inside the first scenario
    preparation.
    """

    def test_all_reachable_returns_normally(self, cli, monkeypatch):
        monkeypatch.setattr(cli.psycopg, "connect", lambda *a, **k: _NullContext())
        fake_driver = Mock()
        monkeypatch.setattr(cli, "GraphDatabase", Mock(driver=lambda *a, **k: fake_driver))
        monkeypatch.setattr(cli.MQTTClient, "connect", lambda self: None)
        monkeypatch.setattr(cli.MQTTClient, "disconnect", lambda self: None)

        cli._check_infrastructure_reachable(_FakeSettings())  # must not raise

    def test_unreachable_postgres_is_reported_by_name(self, cli, monkeypatch):
        def fake_connect(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr(cli.psycopg, "connect", fake_connect)
        fake_driver = Mock()
        monkeypatch.setattr(cli, "GraphDatabase", Mock(driver=lambda *a, **k: fake_driver))
        monkeypatch.setattr(cli.MQTTClient, "connect", lambda self: None)
        monkeypatch.setattr(cli.MQTTClient, "disconnect", lambda self: None)

        with pytest.raises(SystemExit, match="PostgreSQL"):
            cli._check_infrastructure_reachable(_FakeSettings())

    def test_unreachable_neo4j_is_reported_by_name(self, cli, monkeypatch):
        monkeypatch.setattr(cli.psycopg, "connect", lambda *a, **k: _NullContext())

        def fake_driver(*a, **k):
            raise RuntimeError("service unavailable")

        monkeypatch.setattr(cli, "GraphDatabase", Mock(driver=fake_driver))
        monkeypatch.setattr(cli.MQTTClient, "connect", lambda self: None)
        monkeypatch.setattr(cli.MQTTClient, "disconnect", lambda self: None)

        with pytest.raises(SystemExit, match="Neo4j"):
            cli._check_infrastructure_reachable(_FakeSettings())

    def test_unreachable_mqtt_is_reported_by_name(self, cli, monkeypatch):
        monkeypatch.setattr(cli.psycopg, "connect", lambda *a, **k: _NullContext())
        fake_driver = Mock()
        monkeypatch.setattr(cli, "GraphDatabase", Mock(driver=lambda *a, **k: fake_driver))

        def fake_connect(self):
            raise OSError("connection refused")

        monkeypatch.setattr(cli.MQTTClient, "connect", fake_connect)

        with pytest.raises(SystemExit, match="MQTT"):
            cli._check_infrastructure_reachable(_FakeSettings())

    def test_all_unreachable_lists_every_problem_in_one_message(self, cli, monkeypatch):
        monkeypatch.setattr(cli.psycopg, "connect", lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
        monkeypatch.setattr(cli, "GraphDatabase", Mock(driver=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no"))))
        monkeypatch.setattr(cli.MQTTClient, "connect", lambda self: (_ for _ in ()).throw(OSError("no")))

        with pytest.raises(SystemExit) as excinfo:
            cli._check_infrastructure_reachable(_FakeSettings())

        message = str(excinfo.value)
        assert "PostgreSQL" in message
        assert "Neo4j" in message
        assert "MQTT" in message
        assert "docker compose up -d" in message


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False
