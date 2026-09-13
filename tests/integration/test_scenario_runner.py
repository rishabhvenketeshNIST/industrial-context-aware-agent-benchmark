"""
Integration test proving the D3/D4 benchmark scenarios' ground truth is
empirically real, not asserted-and-hoped: running them against the real
simulator + real historian/knowledge graph produces an actual, retrievable
historical trend and actual deviations in the declared affected
measurements.
"""

from datetime import timedelta

from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.environment_loader import EnvironmentLoader
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.runner import ScenarioRunner
from icab.tep import TEPContextSync

DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "icabpassword"

SCENARIOS_DIR = "configs/benchmark/scenarios"


def _runner():
    historian = HistorianService(PostgresHistorianRepository(DATABASE_URL))
    kg_repository = Neo4jKnowledgeGraphRepository(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
    )
    knowledge_graph = KnowledgeGraphService(kg_repository)

    sync = TEPContextSync(
        environment_loader=EnvironmentLoader(
            historian=historian,
            knowledge_graph=knowledge_graph,
        ),
    )

    return ScenarioRunner(context_sync=sync), historian, kg_repository


def test_d3_scenario_produces_a_real_retrievable_pressure_trend():
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d3_reactor_pressure_deviation")

    runner, historian, kg_repository = _runner()

    try:
        result = runner.prepare(scenario)

        assert result.sync_count > 10  # a real, multi-point trend exists

        measurement_id = "urn:icab:measurement:reactor_pressure"

        start = result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)

        history = historian.get_historical_values(measurement_id, start, end)

        assert len(history) > 10

        history_sorted = sorted(history, key=lambda observation: observation.timestamp)
        first_value = history_sorted[0].value
        last_value = history_sorted[-1].value

        # Ground truth direction: reactor pressure declines after IDV(1).
        assert last_value < first_value - 5.0

        # Fault-injection bookkeeping actually happened.
        fault_events = [e for e in result.events if e["type"] == "fault_injected"]
        assert fault_events[0]["disturbance"] == "idv_01"
    finally:
        kg_repository.close()


def test_d4_scenario_deviation_is_downstream_not_in_the_reactor():
    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d4_plant_wide_investigation")

    runner, historian, kg_repository = _runner()

    try:
        result = runner.prepare(scenario)

        start = result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)

        def trend(measurement_id: str) -> tuple[float, float]:
            history = sorted(
                historian.get_historical_values(measurement_id, start, end),
                key=lambda observation: observation.timestamp,
            )
            return history[0].value, history[-1].value

        reactor_first, reactor_last = trend("urn:icab:measurement:reactor_pressure")
        stripper_first, stripper_last = trend("urn:icab:measurement:stripper_level")
        compressor_first, compressor_last = trend("urn:icab:measurement:compressor_work")

        # Ground truth: the reactor itself stays close to normal ...
        assert abs(reactor_last - reactor_first) < 10.0

        # ... while the declared downstream equipment shows a real, large
        # deviation -- confirming this scenario cannot be solved by
        # keyword-matching "reactor" in the objective (it isn't named, and
        # it isn't where the effect is).
        assert stripper_last < stripper_first - 15.0
        assert compressor_last < compressor_first - 15.0
    finally:
        kg_repository.close()


def test_d3_stochastic_scenario_shows_a_gradual_not_instantaneous_deviation():
    """M13-C: the historical-reasoning D3 scenario built on idv_08 --
    confirms its own claimed effect (reactor_pressure decline) is real
    for its own seed, AND that the deviation is gradual (the LATE
    quarter of the window's own mean differs substantially from the
    EARLY quarter's own mean) rather than an instantaneous step --
    the property this scenario specifically exists to test. Compares
    segment MEANS (not single points, which are too noisy for a ~1-2 kPa
    signal) within this one run -- no separate baseline run needed to
    show the value is still developing, not merely to show it moved."""

    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d3_stochastic_composition_drift")

    runner, historian, kg_repository = _runner()

    try:
        result = runner.prepare(scenario)

        measurement_id = "urn:icab:measurement:reactor_pressure"
        start = result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)

        history = sorted(
            historian.get_historical_values(measurement_id, start, end),
            key=lambda observation: observation.timestamp,
        )
        assert len(history) > 10

        values = [observation.value for observation in history]
        quarter = max(1, len(values) // 4)
        early_mean = sum(values[:quarter]) / quarter
        late_mean = sum(values[-quarter:]) / quarter

        # The gradual/stochastic signature: the window's own late segment
        # has drifted substantially further from its own early segment --
        # a real, developing decline (tens of kPa), not noise.
        assert late_mean < early_mean - 10.0

        fault_events = [e for e in result.events if e["type"] == "fault_injected"]
        assert fault_events[0]["disturbance"] == "idv_08"
    finally:
        kg_repository.close()


def test_d4_feed_disturbance_scenario_leaves_the_feed_system_itself_unaffected():
    """M13-C: the 'affected equipment not obvious from the fault's own
    name' D4 scenario built on idv_24 -- confirms the feed system's OWN
    measurement stays essentially flat while reactor/separator/stripper
    pressure genuinely shift, for this scenario's own seed. (The real
    direction at this seed is a RISE, not a decline -- checked directly
    here rather than assumed; see docs/architecture/tep-fault-injection.md
    for why direction, not just magnitude, must be verified empirically.)"""

    registry = BenchmarkScenarioRegistry(SCENARIOS_DIR)
    scenario = registry.get("d4_feed_pressure_reactor_effect")

    runner, historian, kg_repository = _runner()

    try:
        result = runner.prepare(scenario)

        start = result.simulator.epoch
        end = start + timedelta(hours=scenario.warmup_hours + scenario.duration_hours)

        def segment_means(measurement_id: str) -> tuple[float, float]:
            history = sorted(
                historian.get_historical_values(measurement_id, start, end),
                key=lambda observation: observation.timestamp,
            )
            values = [observation.value for observation in history]
            quarter = max(1, len(values) // 4)
            return sum(values[:quarter]) / quarter, sum(values[-quarter:]) / quarter

        feed_d_early, feed_d_late = segment_means("urn:icab:measurement:feed_d_flow")
        reactor_early, reactor_late = segment_means("urn:icab:measurement:reactor_pressure")
        separator_early, separator_late = segment_means("urn:icab:measurement:separator_pressure")

        # Ground truth: the NAMED system (feed) stays close to normal ...
        relative_feed_change = abs(feed_d_late - feed_d_early) / max(abs(feed_d_early), 1e-9)
        assert relative_feed_change < 0.05

        # ... while the declared, unrelated-by-name equipment shows the
        # real, measurable deviation (a rise, at this seed).
        assert reactor_late > reactor_early + 5.0
        assert separator_late > separator_early + 5.0

        fault_events = [e for e in result.events if e["type"] == "fault_injected"]
        assert fault_events[0]["disturbance"] == "idv_24"
    finally:
        kg_repository.close()
