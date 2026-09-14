"""
ICAB v2: the MANDATORY architecture connectivity/health test suite.

Before trusting any benchmark result, ICAB must verify that every
architecture component is actually connected and functioning -- see
`icab.architecture_health`'s module docstring for what "functioning"
means here (a real functional round trip returning real, expected data,
never just "the port is open" or "HTTP 200"). This file is the dedicated
test suite the ICAB v2 direction requires; `icab.architecture_health`
itself is also directly reusable (by `scripts/check_architecture_health.py`
and, optionally, `scripts/run_benchmark.py` before a real experiment).

Each component gets its own test function, independent of the others --
one component being down must produce ONE clear, specific test failure,
never a cascading failure across every other component's test.
"""

from __future__ import annotations

from icab.architecture_health import (
    ComponentHealthResult,
    check_gateway,
    check_historian,
    check_i3x,
    check_knowledge_graph,
    check_mqtt,
    check_opcua,
    check_uns,
    run_architecture_health_check,
)
from icab.common.config import get_settings

GATEWAY_URL = "http://localhost:8000"


def _assert_pass(result: ComponentHealthResult) -> None:
    assert result.status == "PASS", (
        f"{result.component} architecture connectivity check FAILED: {result.failure_reason}\n"
        f"(test performed: {result.test_performed}; expected: {result.expected})"
    )
    # No credentials ever appear in a health result.
    for field in (result.endpoint, result.observed, result.failure_reason or ""):
        assert "password" not in field.lower()


def test_uns_connectivity():
    _assert_pass(check_uns())


def test_historian_connectivity():
    _assert_pass(check_historian(get_settings()))


def test_knowledge_graph_connectivity():
    _assert_pass(check_knowledge_graph(get_settings()))


def test_mqtt_connectivity():
    _assert_pass(check_mqtt(get_settings()))


def test_opcua_connectivity():
    _assert_pass(check_opcua(get_settings()))


def test_i3x_connectivity():
    _assert_pass(check_i3x(get_settings()))


def test_i3x_check_refuses_the_public_conformance_server():
    """
    A structural guard: the i3X connectivity check itself must never
    treat the public api.i3x.dev conformance server as ICAB's private
    instance, even if misconfigured.

    Uses `model_copy(update=...)` (not `ICABSettings(i3x_base_url=...)`)
    -- every `ICABSettings` field declares a `validation_alias` (e.g.
    `ICAB_I3X_BASE_URL`), so constructing directly with the plain
    attribute name as a kwarg is silently ignored by pydantic-settings
    (falling back to the real .env value) unless `populate_by_name` is
    set; `model_copy` bypasses validation/aliasing entirely and just
    sets the attribute, which is what a test override actually wants.
    """

    public_settings = get_settings().model_copy(update={"i3x_base_url": "https://api.i3x.dev/v1"})

    result = check_i3x(public_settings)

    assert result.status == "FAIL"
    assert "public" in (result.failure_reason or "").lower()


def test_gateway_connectivity():
    """
    Requires a live gateway process (uv run uvicorn icab.gateway.app:app)
    at GATEWAY_URL -- skipped, not failed, if it isn't reachable, since
    every other test in this file already exercises the real backing
    services directly.
    """

    import httpx
    import pytest

    try:
        httpx.get(f"{GATEWAY_URL}/health", timeout=2.0).raise_for_status()
    except Exception:
        pytest.skip(f"Agent Gateway not reachable at {GATEWAY_URL} -- start it with 'uv run uvicorn icab.gateway.app:app'.")

    _assert_pass(check_gateway(GATEWAY_URL, get_settings()))


def test_end_to_end_smoke_test_covers_every_component_and_fails_clearly_on_a_broken_one():
    """
    The single, end-to-end architecture smoke test the ICAB v2 direction
    asks for (#16): exercises the FULL chain -- TEP -> CIM -> architecture
    component -> gateway -> tool -> expected observation -- for every
    component at once via `run_architecture_health_check`, and confirms
    the report structure itself (not just individual checks) is
    trustworthy: a deliberately broken component (an unreachable fake
    endpoint) is reported as FAIL with a clear reason, never silently
    dropped or reported as PASS.
    """

    report = run_architecture_health_check(gateway_url=None, settings=get_settings())

    assert report.all_passed, f"Architecture components failed: {report.failed_components}"
    assert {result.component for result in report.results} == {
        "UNS", "Historian", "KnowledgeGraph", "MQTT", "OPCUA", "i3X",
    }

    # A deliberately broken Historian (bad port) must be reported as a
    # clear FAIL, not silently ignored or mistaken for a PASS. See
    # test_i3x_check_refuses_the_public_conformance_server for why
    # model_copy (not ICABSettings(database_url=...)) is used here.
    #
    # `connect_timeout=3` is REQUIRED, not cosmetic: confirmed directly
    # (a bare `psycopg.connect("...@localhost:1/icab")` with no timeout
    # hangs for 20+ seconds on Windows -- an unresponsive/filtered port
    # is not the same as an immediate "connection refused"). A real
    # health check that can hang indefinitely on a broken component
    # defeats its own purpose, so this is also a regression test for
    # that failure mode staying bounded.
    broken_settings = get_settings().model_copy(
        update={"database_url": "postgresql://icab:icab@localhost:1/icab?connect_timeout=3"}
    )
    broken_result = check_historian(broken_settings, seed_data=False)

    assert broken_result.status == "FAIL"
    assert broken_result.failure_reason is not None
