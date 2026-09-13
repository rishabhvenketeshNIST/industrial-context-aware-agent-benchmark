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

import uuid
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
    #: Provenance tag shared by every observation/relationship this
    #: preparation wrote (see `ScenarioRunner.prepare` and
    #: `icab.evaluation.grounded.GroundedInvestigationEvaluator`'s
    #: `generation_id` parameter) -- lets a benchmark run distinguish its
    #: own data from an unrelated run's leftovers in the same shared,
    #: persistent historian/knowledge graph.
    generation_id: str = ""
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

        # One generation_id per preparation, shared by every sync() call
        # below (and, in turn, every observation/relationship they write) --
        # the provenance tag that lets this run's data be told apart from
        # an unrelated run's leftovers in the same shared, persistent
        # historian/knowledge graph. See ExperimentRunner/
        # GroundedInvestigationEvaluator's generation_id parameter.
        generation_id = uuid.uuid4().hex

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

        # M13-B: faults with a `duration_hours` are cleared at
        # activate_at_hours + duration_hours (deactivated, not merely
        # left at magnitude -- inject_fault(active=False) zeroes the
        # disturbance vector entry) rather than staying active for the
        # rest of the scenario -- pre-M13-B behavior (duration_hours is
        # None) is unchanged: once activated, never cleared.
        pending_deactivations = sorted(
            (
                (fault.activate_at_hours + fault.duration_hours, fault.disturbance)
                for fault in scenario.faults
                if fault.duration_hours is not None
            ),
            key=lambda item: item[0],
        )
        deactivation_index = 0

        self.context_sync.sync(simulator, generation_id=generation_id)
        sync_count += 1

        while elapsed < total_hours - 1e-9:
            while (
                fault_index < len(pending_faults)
                and pending_faults[fault_index].activate_at_hours <= elapsed + 1e-9
            ):
                fault = pending_faults[fault_index]
                simulator.inject_fault(fault.disturbance, magnitude=fault.magnitude)
                fault_index += 1

            while (
                deactivation_index < len(pending_deactivations)
                and pending_deactivations[deactivation_index][0] <= elapsed + 1e-9
            ):
                _, disturbance = pending_deactivations[deactivation_index]
                simulator.inject_fault(disturbance, active=False)
                deactivation_index += 1

            step = min(scenario.sync_interval_hours, total_hours - elapsed)
            simulator.step(duration=step)
            elapsed += step

            environment = self.context_sync.sync(simulator, generation_id=generation_id)
            sync_count += 1

        return ScenarioRunResult(
            scenario=scenario,
            simulator=simulator,
            environment=environment,
            generation_id=generation_id,
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
