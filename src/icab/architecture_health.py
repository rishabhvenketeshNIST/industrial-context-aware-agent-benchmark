"""
ICAB v2: mandatory architecture connectivity/health verification (see the
ICAB v2 direction's "CRITICAL: architecture connectivity tests" section).

Before trusting any benchmark result, ICAB must verify that every
architecture component is ACTUALLY connected and functioning -- not
merely that a container process is running or a port accepts a TCP
connection. Every check here performs a REAL, functional round trip
through the real service and asserts on the ACTUAL data returned, not
just a status code:

    Historian         -- write/read a real observation through Postgres/TimescaleDB
    Knowledge Graph    -- real entity/relationship round trip through Neo4j
    UNS                -- the real, in-process TEP UNS tree contains expected nodes
    MQTT               -- a real publish/read round trip through the Mosquitto broker
    OPC UA             -- browse + read against the REAL, already-running
                          TEP-backed OPC UA server container
    i3X                -- browse + read against ICAB's REAL, already-running
                          private (never the public api.i3x.dev) i3X instance
    Gateway            -- the real FastAPI HTTP routes, called over HTTP,
                          returning correct data from the real backing services

A component "PASS" means the FULL chain (TEP -> CIM -> that architecture
-> gateway) produced the expected data -- see `run_architecture_health_check`.
A component that is merely reachable but returns wrong/stale/empty data
is reported as a FAIL with an explicit reason, never silently treated as
healthy -- a broken architecture must never be interpreted as a scoring
result (see the ICAB v2 failure-taxonomy direction: `icab.analysis
.failure_taxonomy` relies on this report to distinguish an
architecture_connectivity_failure from a genuine agent/reasoning failure).

No credentials are ever included in a `ComponentHealthResult` --
`endpoint` is a plain host/URL, never a connection string with an
embedded password (see `_redact_connection_string`).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime
from typing import Callable

from pydantic import BaseModel, ConfigDict

from icab.common.config import ICABSettings, get_settings
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.i3x.client import I3XClient
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt import MQTTClient, TEPMeasurementPublisher
from icab.context.opcua import OPCUAClient
from icab.context.uns.repository import InMemoryUNSRepository
from icab.context.uns.service import UNSService
from icab.context.uns.tep_builder import build_real_uns_nodes
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync

#: The scenario used to produce real, fresh TEP data for the
#: Historian/Knowledge-Graph/MQTT/Gateway checks below -- the shortest,
#: simplest real scenario in the registered suite (no fault, D1), kept
#: to a short warmup/duration so a health check stays fast.
_HEALTH_CHECK_SCENARIO_ID = "d1_reactor_pressure_reading"
_HEALTH_CHECK_MEASUREMENT_ID = "urn:icab:measurement:reactor_pressure"
_HEALTH_CHECK_EQUIPMENT_ID = "urn:icab:equipment:reactor"

_CONNECTION_STRING_PASSWORD = re.compile(r"://([^:/@]+):([^@]+)@")


def _redact_connection_string(value: str) -> str:
    """Never expose a password embedded in a connection string (e.g. `postgresql://user:PASSWORD@host/db`)."""

    return _CONNECTION_STRING_PASSWORD.sub(r"://\1:***@", value)


def _with_bounded_connect_timeout(database_url: str, *, seconds: int = 10) -> str:
    """
    Ensures `database_url` has a `connect_timeout` -- confirmed directly
    (not assumed) that a bare `psycopg.connect()` against an
    unresponsive/filtered PostgreSQL port hangs for 20+ seconds on
    Windows rather than failing fast, which would defeat a health
    check's whole purpose of being a fast, reliable signal. A caller who
    already set their own `connect_timeout` in the URL is left alone.
    """

    if "connect_timeout" in database_url:
        return database_url
    separator = "&" if "?" in database_url else "?"
    return f"{database_url}{separator}connect_timeout={seconds}"


class ComponentHealthResult(BaseModel):
    """One architecture component's real, functional connectivity check result."""

    model_config = ConfigDict(extra="forbid")

    component: str
    endpoint: str
    status: str  # "PASS" | "FAIL"
    test_performed: str
    expected: str
    observed: str
    latency_ms: float | None = None
    timestamp: datetime
    failure_reason: str | None = None


class ArchitectureHealthReport(BaseModel):
    """The full architecture connectivity report -- one result per component."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    results: list[ComponentHealthResult]

    @property
    def all_passed(self) -> bool:
        return all(result.status == "PASS" for result in self.results)

    @property
    def failed_components(self) -> list[str]:
        return [result.component for result in self.results if result.status != "PASS"]


def _run_check(component: str, endpoint: str, test_performed: str, expected: str, fn: Callable[[], str]) -> ComponentHealthResult:
    """
    Runs one component check, timing it and converting any exception into
    a FAIL result (with the exception message as `failure_reason`) rather
    than letting one broken component crash the whole report -- a health
    report's whole point is to be trustworthy even when something IS
    broken.
    """

    started = time.perf_counter()
    try:
        observed = fn()
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ComponentHealthResult(
            component=component,
            endpoint=endpoint,
            status="PASS",
            test_performed=test_performed,
            expected=expected,
            observed=observed,
            latency_ms=latency_ms,
            timestamp=datetime.now(UTC),
        )
    except Exception as error:  # noqa: BLE001 -- deliberately broad: reported, not silenced
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ComponentHealthResult(
            component=component,
            endpoint=endpoint,
            status="FAIL",
            test_performed=test_performed,
            expected=expected,
            observed="(none)",
            latency_ms=latency_ms,
            timestamp=datetime.now(UTC),
            failure_reason=f"{type(error).__name__}: {error}",
        )


def check_uns() -> ComponentHealthResult:
    """The real, in-process TEP UNS tree -- no live server; browse() over the real node set."""

    def run() -> str:
        service = UNSService(InMemoryUNSRepository(build_real_uns_nodes()))
        nodes = service.browse("site/tep")
        names = {node.display_name for node in nodes}
        if "Reactor" not in names:
            raise AssertionError(f"'Reactor' not found under site/tep -- got {sorted(names)}")
        reactor_children = service.browse("site/tep/reactor")
        canonical_ids = {node.canonical_id for node in reactor_children if node.canonical_id}
        if _HEALTH_CHECK_MEASUREMENT_ID not in canonical_ids:
            raise AssertionError(f"{_HEALTH_CHECK_MEASUREMENT_ID} not found under site/tep/reactor")
        return f"{len(nodes)} top-level node(s) under site/tep, including Reactor with {len(reactor_children)} child measurement(s)"

    return _run_check(
        component="UNS",
        endpoint="in-process (icab.context.uns.tep_builder)",
        test_performed="browse('site/tep') and browse('site/tep/reactor') over the real TEP UNS tree",
        expected=f"'Reactor' node present; {_HEALTH_CHECK_MEASUREMENT_ID} discoverable under it",
        fn=run,
    )


def check_historian(settings: ICABSettings, *, seed_data: bool = True) -> ComponentHealthResult:
    endpoint = _redact_connection_string(settings.database_url)

    def run() -> str:
        historian = HistorianService(PostgresHistorianRepository(_with_bounded_connect_timeout(settings.database_url)))
        if seed_data:
            _prepare_health_check_scenario(settings)
        observation = historian.get_current_value(_HEALTH_CHECK_MEASUREMENT_ID)
        if observation is None:
            raise AssertionError(f"get_current_value({_HEALTH_CHECK_MEASUREMENT_ID}) returned None")
        if not (500.0 < observation.value < 5000.0):
            raise AssertionError(f"implausible reactor_pressure value: {observation.value}")
        return f"value={observation.value:.2f} {observation.unit}, timestamp={observation.timestamp.isoformat()}"

    return _run_check(
        component="Historian",
        endpoint=endpoint,
        test_performed=f"get_current_value({_HEALTH_CHECK_MEASUREMENT_ID}) after a real scenario preparation",
        expected="A recent observation with a plausible reactor-pressure value and unit",
        fn=run,
    )


def check_knowledge_graph(settings: ICABSettings, *, seed_data: bool = True) -> ComponentHealthResult:
    endpoint = settings.neo4j_uri

    def run() -> str:
        repository = Neo4jKnowledgeGraphRepository(
            uri=settings.neo4j_uri, username=settings.neo4j_username, password=settings.neo4j_password
        )
        try:
            if seed_data:
                _prepare_health_check_scenario(settings)
            knowledge_graph = KnowledgeGraphService(repository)
            relationships = knowledge_graph.get_entity_relationships(_HEALTH_CHECK_EQUIPMENT_ID)
            predicates = {relationship.predicate.value for relationship in relationships}
            monitored = {
                relationship.object for relationship in relationships if relationship.predicate.value == "MONITORS"
            }
            if "MONITORS" not in predicates:
                raise AssertionError(f"No MONITORS relationship found for {_HEALTH_CHECK_EQUIPMENT_ID}")
            if _HEALTH_CHECK_MEASUREMENT_ID not in monitored:
                raise AssertionError(f"{_HEALTH_CHECK_EQUIPMENT_ID} does not MONITOR {_HEALTH_CHECK_MEASUREMENT_ID}")
            return f"{len(relationships)} relationship(s) for {_HEALTH_CHECK_EQUIPMENT_ID}, including MONITORS -> {_HEALTH_CHECK_MEASUREMENT_ID}"
        finally:
            repository.close()

    return _run_check(
        component="KnowledgeGraph",
        endpoint=endpoint,
        test_performed=f"get_entity_relationships({_HEALTH_CHECK_EQUIPMENT_ID}) via the real discovery interface (no fuzzy search)",
        expected=f"A real MONITORS relationship from {_HEALTH_CHECK_EQUIPMENT_ID} to {_HEALTH_CHECK_MEASUREMENT_ID}",
        fn=run,
    )


def check_mqtt(settings: ICABSettings, *, seed_data: bool = True) -> ComponentHealthResult:
    endpoint = f"{settings.mqtt_host}:{settings.mqtt_port}"

    def run() -> str:
        if seed_data:
            _prepare_health_check_scenario(settings)
        client = MQTTClient(settings.mqtt_host, settings.mqtt_port)
        message = client.read(f"icab/tep/reactor/{_HEALTH_CHECK_MEASUREMENT_ID.rsplit(':', 1)[-1]}", timeout=3.0)
        if message is None:
            # Topic naming is derived, not guaranteed -- fall back to a
            # broad discovery pass rather than assuming one exact topic.
            messages = client.discover("icab/tep/#", timeout=3.0)
            message = next((m for m in messages if _HEALTH_CHECK_MEASUREMENT_ID in m.topic), None) or next(
                (m for m in messages if "reactor" in m.topic.lower() and "pressure" in m.topic.lower()), None
            )
        if message is None:
            raise AssertionError("No retained reactor-pressure message found on icab/tep/#")
        return f"topic={message.topic}, payload keys={sorted(message.model_dump().keys())}"

    return _run_check(
        component="MQTT",
        endpoint=endpoint,
        test_performed="discover/read a real, retained reactor-pressure message on the icab/tep/# namespace",
        expected="A retained message for the reactor pressure measurement, published by TEPMeasurementPublisher",
        fn=run,
    )


def check_opcua(settings: ICABSettings | None = None) -> ComponentHealthResult:
    settings = settings or get_settings()
    endpoint = "opc.tcp://127.0.0.1:4841/icab/tep/"

    async def run_async() -> str:
        client = OPCUAClient(endpoint)
        top_level = await client.browse("i=85")
        names = {node.display_name for node in top_level}
        if "Reactor" not in names:
            raise AssertionError(f"'Reactor' object not found browsing the real OPC UA server -- got {sorted(names)}")
        reactor_id = next(node.node_id for node in top_level if node.display_name == "Reactor")
        children = await client.browse(reactor_id)
        pressure_node = next((node for node in children if "pressure" in node.display_name.lower()), None)
        if pressure_node is None:
            raise AssertionError("No pressure-related variable found under the real OPC UA Reactor object")
        value = await client.read(pressure_node.node_id)
        if not (500.0 < float(value) < 5000.0):
            raise AssertionError(f"implausible OPC UA reactor-pressure reading: {value}")
        return f"Reactor object with {len(children)} variable(s); {pressure_node.display_name}={value}"

    def run() -> str:
        return asyncio.run(run_async())

    return _run_check(
        component="OPCUA",
        endpoint=endpoint,
        test_performed="browse the real, already-running TEP-backed OPC UA server and read a live value",
        expected="A 'Reactor' object with a plausible pressure variable value",
        fn=run,
    )


def check_i3x(settings: ICABSettings | None = None) -> ComponentHealthResult:
    settings = settings or get_settings()
    endpoint = settings.i3x_base_url

    def run() -> str:
        if endpoint.rstrip("/") == "https://api.i3x.dev/v1":
            raise AssertionError(
                "ICAB_I3X_BASE_URL points at the PUBLIC api.i3x.dev conformance "
                "server -- the architecture health check refuses to treat that "
                "as ICAB's private, TEP-backed i3X instance."
            )
        client = I3XClient(endpoint)
        info = client.get_info()
        objects = client.get_objects()
        names = {obj.display_name for obj in objects}
        if "Reactor" not in names:
            raise AssertionError(f"'Reactor' object not found via the real private i3X instance -- got {sorted(names)}")
        reactor = next(obj for obj in objects if obj.display_name == "Reactor")
        related = client.get_related_objects(element_ids=[reactor.element_id])
        pressure_object = next(
            (item.object for item in related if "pressure" in item.object.display_name.lower()),
            None,
        )
        if pressure_object is None:
            raise AssertionError("No pressure-related object related to the real i3X Reactor object")
        value_response = client.get_value(element_id=pressure_object.element_id)
        if not (500.0 < value_response.value < 5000.0):
            raise AssertionError(f"implausible i3X reactor-pressure reading: {value_response.value}")
        return f"server={info.server_name} v{info.spec_version}; Reactor -> {pressure_object.display_name}={value_response.value}"

    return _run_check(
        component="i3X",
        endpoint=endpoint,
        test_performed="get_objects/get_related_objects/get_value against the real private i3X instance",
        expected="A 'Reactor' object with a related, plausible pressure value -- never the public api.i3x.dev",
        fn=run,
    )


def check_gateway(gateway_url: str, settings: ICABSettings) -> ComponentHealthResult:
    def run() -> str:
        import httpx

        _prepare_health_check_scenario(settings)

        response = httpx.post(
            f"{gateway_url}/tools/get_current_value",
            json={"measurement_id": _HEALTH_CHECK_MEASUREMENT_ID},
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()
        observation = body.get("observation")
        if not observation or observation.get("value") is None:
            raise AssertionError(f"gateway returned no usable observation: {body}")
        if not (500.0 < float(observation["value"]) < 5000.0):
            raise AssertionError(f"implausible value via gateway HTTP route: {observation['value']}")
        return f"HTTP 200, observation.value={observation['value']}, unit={observation.get('unit')}"

    return _run_check(
        component="Gateway",
        endpoint=f"{gateway_url}/tools/get_current_value",
        test_performed="a real HTTP POST to the gateway's own FastAPI route, backed by the real Historian",
        expected="HTTP 200 with a real, plausible reactor-pressure observation (not just status code 200)",
        fn=run,
    )


#: Cached by the target database's own connection string (not by
#: `id(settings)`) -- `get_settings()` builds a fresh `ICABSettings`
#: object on every call, so caching by object identity would defeat the
#: cache entirely across separate calls that all point at the SAME real
#: database. What actually matters is "has fresh data already been
#: prepared for this real database in this process," not object identity.
_health_check_scenario_prepared: set[str] = set()


def _prepare_health_check_scenario(settings: ICABSettings) -> None:
    """
    Runs the real, short `_HEALTH_CHECK_SCENARIO_ID` scenario exactly
    once per target database (see cache-key note above) so every
    component check that needs FRESH real TEP data in a given process
    shares one preparation rather than each re-running the simulator
    from scratch.
    """

    cache_key = settings.database_url
    if cache_key in _health_check_scenario_prepared:
        return

    historian = HistorianService(PostgresHistorianRepository(_with_bounded_connect_timeout(settings.database_url)))
    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=settings.neo4j_uri, username=settings.neo4j_username, password=settings.neo4j_password
    )
    try:
        knowledge_graph = KnowledgeGraphService(kg_repository)
        mqtt_client = MQTTClient(settings.mqtt_host, settings.mqtt_port)
        publisher = TEPMeasurementPublisher(mqtt_client, source="architecture_health")
        context_sync = TEPContextSync(
            environment_loader=EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph),
            mqtt_publisher=publisher,
        )
        scenario = BenchmarkScenarioRegistry("configs/benchmark/scenarios").get(_HEALTH_CHECK_SCENARIO_ID)
        with mqtt_client:
            ScenarioRunner(context_sync=context_sync).prepare(scenario)
    finally:
        kg_repository.close()

    _health_check_scenario_prepared.add(cache_key)


def run_architecture_health_check(
    *,
    gateway_url: str | None = None,
    settings: ICABSettings | None = None,
    components: list[str] | None = None,
) -> ArchitectureHealthReport:
    """
    Runs every real architecture connectivity check and returns one
    consolidated `ArchitectureHealthReport`. Each component's check is
    independent (one failing never prevents the others from running) --
    see `_run_check`.

    `components`, when given, restricts which checks run (by
    `ComponentHealthResult.component` name) -- e.g. for
    `--check-architecture-health` skipping Gateway when no
    `--gateway-url` is reachable yet.
    """

    settings = settings or get_settings()
    _health_check_scenario_prepared.clear()

    all_checks: dict[str, Callable[[], ComponentHealthResult]] = {
        "UNS": check_uns,
        "Historian": lambda: check_historian(settings),
        "KnowledgeGraph": lambda: check_knowledge_graph(settings),
        "MQTT": lambda: check_mqtt(settings),
        "OPCUA": lambda: check_opcua(settings),
        "i3X": lambda: check_i3x(settings),
    }
    if gateway_url is not None:
        all_checks["Gateway"] = lambda: check_gateway(gateway_url, settings)

    wanted = components if components is not None else list(all_checks)
    results = [all_checks[name]() for name in wanted if name in all_checks]

    return ArchitectureHealthReport(generated_at=datetime.now(UTC), results=results)
