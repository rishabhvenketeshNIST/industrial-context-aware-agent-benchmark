"""
Prepares the real TEP simulator + industrial context architectures for a
:class:`~icab.scenarios.models.BenchmarkScenario`, deterministically.

This is the piece that turns a scenario definition into an actual running
plant an agent can investigate: reset the simulator with the scenario's
seed, let it settle through an optional warmup, activate any scheduled
faults at the right simulated time, and periodically push snapshots into
the historian/knowledge graph/MQTT (via ``TEPContextSync``) so a D3/D4
scenario's historical/relational evidence genuinely exists to be
retrieved, rather than only a single final snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from icab.cim import CIMEnvironment
from icab.tep.context_sync import TEPContextSync
from icab.tep.simulator import TEPSimulator

from .models import BenchmarkScenario

#: Reference date scenario epochs are offset from (see `_epoch_for`).
_EPOCH_BASE = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class ScenarioRunResult:
    """The prepared, ready-to-investigate state of one scenario run."""

    scenario: BenchmarkScenario
    simulator: TEPSimulator
    environment: CIMEnvironment
    events: list[dict[str, Any]] = field(default_factory=list)
    sync_count: int = 0


class ScenarioRunner:
    """Deterministically prepares a BenchmarkScenario against a real TEPSimulator."""

    def __init__(self, *, context_sync: TEPContextSync) -> None:
        self.context_sync = context_sync

    def prepare(self, scenario: BenchmarkScenario) -> ScenarioRunResult:
        """
        Reset, warm up, run (activating scheduled faults), and periodically
        sync a fresh simulator for ``scenario``. Returns the final state.
        """

        simulator = TEPSimulator(epoch=self._epoch_for(scenario))
        simulator.reset(seed=scenario.seed)

        elapsed = 0.0
        sync_count = 0

        # Warmup: let the closed loop settle before anything is recorded,
        # so historian data reflects only the scenario's own timeline.
        while elapsed < scenario.warmup_hours - 1e-9:
            step = min(scenario.sync_interval_hours, scenario.warmup_hours - elapsed)
            simulator.step(duration=step)
            elapsed += step

        pending_faults = sorted(scenario.faults, key=lambda fault: fault.activate_at_hours)
        fault_index = 0
        total_hours = scenario.warmup_hours + scenario.duration_hours

        self.context_sync.sync(simulator)
        sync_count += 1

        while elapsed < total_hours - 1e-9:
            while (
                fault_index < len(pending_faults)
                and pending_faults[fault_index].activate_at_hours <= elapsed + 1e-9
            ):
                fault = pending_faults[fault_index]
                simulator.inject_fault(fault.disturbance, magnitude=fault.magnitude)
                fault_index += 1

            step = min(scenario.sync_interval_hours, total_hours - elapsed)
            simulator.step(duration=step)
            elapsed += step

            environment = self.context_sync.sync(simulator)
            sync_count += 1

        return ScenarioRunResult(
            scenario=scenario,
            simulator=simulator,
            environment=environment,
            events=simulator.get_events(),
            sync_count=sync_count,
        )

    @staticmethod
    def _epoch_for(scenario: BenchmarkScenario) -> datetime:
        """
        A deterministic, scenario-distinct epoch (day-offset from a fixed
        reference date, keyed by the scenario's seed).

        Historian/MQTT observation identity is timestamp + canonical id
        (see `TEPAdapter.create_real_observation`), and the historian and
        MQTT broker are shared, persistent infrastructure across scenario
        runs -- without a scenario-distinct epoch, two scenarios reaching
        the same *elapsed* simulated hour (a near-certainty, since most
        scenarios share the same warmup/sync-interval conventions) would
        produce identical observation ids with different values, silently
        colliding (`ON CONFLICT ... DO NOTHING` keeps whichever was written
        first). Offsetting by the seed keeps each scenario in its own
        timestamp range while staying fully deterministic/reproducible.
        """

        return _EPOCH_BASE + timedelta(days=scenario.seed)
