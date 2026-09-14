"""
Unit tests for icab.architecture_health's pure helper functions --
`_redact_connection_string`/`_with_bounded_connect_timeout` need no real
infrastructure; the actual per-component checks are covered by
tests/integration/test_architecture_connectivity.py against the real
Docker stack.
"""

from __future__ import annotations

from icab.architecture_health import ArchitectureHealthReport, ComponentHealthResult, _redact_connection_string, _with_bounded_connect_timeout


class TestRedactConnectionString:
    def test_password_is_redacted(self):
        redacted = _redact_connection_string("postgresql://icab:supersecret@localhost:5432/icab")
        assert "supersecret" not in redacted
        assert "icab:***@" in redacted

    def test_username_and_host_are_preserved(self):
        redacted = _redact_connection_string("postgresql://icab:supersecret@localhost:5432/icab")
        assert "icab:" in redacted
        assert "localhost:5432/icab" in redacted

    def test_a_url_with_no_credentials_is_left_alone(self):
        url = "http://localhost:8090"
        assert _redact_connection_string(url) == url

    def test_bolt_uri_with_no_embedded_credentials_is_unaffected(self):
        uri = "bolt://localhost:7687"
        assert _redact_connection_string(uri) == uri


class TestBoundedConnectTimeout:
    def test_adds_connect_timeout_when_absent(self):
        result = _with_bounded_connect_timeout("postgresql://icab:icab@localhost:5432/icab")
        assert "connect_timeout=" in result

    def test_uses_question_mark_when_url_has_no_query_string_yet(self):
        result = _with_bounded_connect_timeout("postgresql://icab:icab@localhost:5432/icab")
        assert "?connect_timeout=" in result

    def test_uses_ampersand_when_url_already_has_a_query_string(self):
        result = _with_bounded_connect_timeout("postgresql://icab:icab@localhost:5432/icab?sslmode=disable")
        assert "&connect_timeout=" in result

    def test_leaves_an_explicit_connect_timeout_alone(self):
        url = "postgresql://icab:icab@localhost:5432/icab?connect_timeout=30"
        assert _with_bounded_connect_timeout(url) == url

    def test_respects_the_seconds_argument(self):
        result = _with_bounded_connect_timeout("postgresql://icab:icab@localhost:5432/icab", seconds=3)
        assert "connect_timeout=3" in result


class TestArchitectureHealthReport:
    def test_all_passed_true_when_every_result_passes(self):
        from datetime import UTC, datetime

        results = [
            ComponentHealthResult(
                component="Historian", endpoint="x", status="PASS", test_performed="t",
                expected="e", observed="o", timestamp=datetime.now(UTC),
            )
        ]
        report = ArchitectureHealthReport(generated_at=datetime.now(UTC), results=results)
        assert report.all_passed is True
        assert report.failed_components == []

    def test_all_passed_false_and_failed_components_populated_on_any_failure(self):
        from datetime import UTC, datetime

        results = [
            ComponentHealthResult(component="Historian", endpoint="x", status="PASS", test_performed="t", expected="e", observed="o", timestamp=datetime.now(UTC)),
            ComponentHealthResult(component="MQTT", endpoint="y", status="FAIL", test_performed="t", expected="e", observed="o", timestamp=datetime.now(UTC), failure_reason="boom"),
        ]
        report = ArchitectureHealthReport(generated_at=datetime.now(UTC), results=results)
        assert report.all_passed is False
        assert report.failed_components == ["MQTT"]
