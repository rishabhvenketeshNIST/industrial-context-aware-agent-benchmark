"""
ICAB process abstraction over a real Tennessee Eastman Process simulator.

This module is the ONLY place in ICAB that imports ``tep_studio``. Every
other component depends on :class:`TEPSimulator`, so the benchmark stays
decoupled from the specific simulator implementation (per the ICAB
architectural principle that the rest of the system should not care which
concrete TEP kernel is behind the process abstraction).

``tep-studio`` (https://github.com/khalidlabs/tep-studio) wraps a native
kernel compiled from ``temexd_mod.c`` -- the widely used C port of the
Downs & Vogel (1993) Tennessee Eastman Process, modified per Bathelt,
Ricker & Jelali (2015). Closed-loop operation uses the decentralized PI
controller described in Ricker, "Decentralized control of the Tennessee
Eastman Challenge Process" (J. Proc. Cont. 6(4), 1996). This is a real,
citable dynamic simulation -- not a fabricated one -- but ICAB makes no
claim beyond what these sources document; see ``docs/`` for the fidelity
notes carried over from Phase 1.

Distinguishing outputs
-----------------------
* **Real simulator output**: measurement values, process time, and shutdown
  ("trip") events all come directly from the wrapped kernel.
* **Benchmark-generated metadata**: fault-injection log entries recorded by
  :meth:`TEPSimulator.inject_fault` are ICAB bookkeeping (tagged
  ``source="icab"`` in :meth:`get_events`) describing when *ICAB* asked the
  simulator to activate a disturbance -- they are not something the plant
  itself reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .state import TEPProcessState

#: Native controller/integrator update rate (hours) the wrapped kernel and
#: its tuned decentralized PI controller were designed and validated at
#: (~1.8 seconds). Coarser control intervals were found, empirically, to
#: destabilize the closed loop -- see the Phase 1 implementation notes.
NATIVE_CONTROL_INTERVAL = 0.0005

#: Default reporting granularity (hours). 0.05 h = 3 minutes, the sampling
#: interval commonly used for published TEP datasets (e.g. Rieth et al.).
DEFAULT_CHECKPOINT_INTERVAL = 0.05


@dataclass(frozen=True)
class TEPEvent:
    """A single simulator or ICAB-generated event."""

    type: str
    source: str  # "simulator" (real kernel output) or "icab" (benchmark metadata)
    time: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "source": self.source, "time": self.time, **self.data}


class TEPSimulator:
    """
    Deterministic, steppable wrapper around the real TEP kernel.

    Conceptually::

        TEPSimulator
        |
        +-- reset(seed)
        +-- step(duration)
        +-- get_state()
        +-- get_measurements()
        +-- inject_fault(...)
        +-- get_events()

    By default the plant runs under closed-loop control (the bundled
    decentralized PI controller), so it behaves like an operating unit
    that a fault perturbs rather than one that trips immediately -- the
    "operator-like starting state" ICAB scenarios assume. Pass
    ``closed_loop=False`` for an open-loop plant (manipulated variables
    held constant), useful for testing raw process dynamics.
    """

    def __init__(
        self,
        *,
        checkpoint_interval: float = DEFAULT_CHECKPOINT_INTERVAL,
        closed_loop: bool = True,
        epoch: datetime | None = None,
    ) -> None:
        from tep_studio import (
            TennesseeEastmanProcess,
            list_disturbances,
            list_manipulated_variables,
            list_measurements,
        )
        from tep_studio.control import RickerMultiLoopController
        from tep_studio.simulation.schema import TEP_SCHEMA

        self._process = TennesseeEastmanProcess()
        self._schema = TEP_SCHEMA
        self._measurement_names = tuple(name for name, _, _ in list_measurements())
        self._manipulated_variable_names = tuple(
            name for name, _, _ in list_manipulated_variables()
        )
        self._disturbance_names = tuple(name for name, _ in list_disturbances())
        self._controller = RickerMultiLoopController() if closed_loop else None

        self.checkpoint_interval = checkpoint_interval
        self._epoch = epoch or datetime(2026, 1, 1, tzinfo=UTC)

        self._seed: int | None = None
        self._disturbances: dict[str, float] = {}
        self._fault_log: list[TEPEvent] = []
        self._last_measurements: Any = None
        self._last_shutdown: dict[str, Any] = {
            "code": 0.0,
            "message": "",
            "terminated": False,
        }
        self._time = 0.0

    # -- lifecycle -----------------------------------------------------

    def reset(self, *, seed: int | None = None) -> TEPProcessState:
        """Reset the plant to the Mode-1 steady state and return the initial state."""

        self._seed = seed
        self._disturbances = {}
        self._fault_log = []
        self._time = 0.0

        measurements, info = self._process.reset(
            seed=float(seed) if seed is not None else None,
        )

        self._last_measurements = measurements
        self._last_shutdown = info["shutdown_status"]

        if self._controller is not None:
            self._controller.reset(measurements, time=0.0)

        return self._build_state()

    def step(self, *, duration: float | None = None) -> TEPProcessState:
        """
        Advance the plant by ``duration`` hours (default: one checkpoint
        interval) and return the resulting state.

        Internally this integrates in native ``NATIVE_CONTROL_INTERVAL``
        substeps (recomputing the controller action, when closed-loop, at
        each substep) so the reported checkpoint can be coarser than the
        kernel's own tuned control rate without destabilizing the plant.
        """

        if self._last_measurements is None:
            raise RuntimeError("TEPSimulator.reset() must be called before step().")

        remaining = self.checkpoint_interval if duration is None else duration
        target_time = self._time + remaining
        eps = NATIVE_CONTROL_INTERVAL * 1e-6

        while self._time < target_time - eps:
            if self._last_shutdown.get("terminated"):
                break

            idv_vector = self._schema.vector("disturbance", self._disturbances)
            interval = min(NATIVE_CONTROL_INTERVAL, target_time - self._time)

            if self._controller is not None:
                action, _diagnostics = self._controller.compute_action(
                    self._last_measurements,
                    time=self._time,
                )
            else:
                action = self._process.state[38:50]

            result = self._process.advance(
                action,
                control_interval=interval,
                disturbances=idv_vector,
            )

            self._time = result.time
            self._last_measurements = result.measurements
            self._last_shutdown = result.shutdown_status

        return self._build_state()

    # -- faults / disturbances ------------------------------------------

    def inject_fault(
        self,
        disturbance: str,
        *,
        active: bool = True,
        magnitude: float = 1.0,
    ) -> None:
        """
        Activate (or clear) one of the 28 published TEP disturbances
        (IDV 1-20 are documented faults; IDV 21-28 are documented random
        variations), e.g. ``inject_fault("idv_01")``.
        """

        if disturbance not in self._disturbance_names:
            raise ValueError(
                f"Unknown TEP disturbance: {disturbance!r}. "
                f"Valid names: {', '.join(self._disturbance_names)}"
            )

        self._disturbances[disturbance] = magnitude if active else 0.0

        self._fault_log.append(
            TEPEvent(
                type="fault_injected",
                source="icab",
                time=self._time,
                data={
                    "disturbance": disturbance,
                    "active": active,
                    "magnitude": magnitude,
                },
            )
        )

    # -- observation -----------------------------------------------------

    def get_state(self) -> TEPProcessState:
        """Return the current process state without advancing simulation time."""

        if self._last_measurements is None:
            raise RuntimeError("TEPSimulator.reset() must be called before get_state().")

        return self._build_state()

    def get_measurements(self) -> dict[str, float]:
        """Return the 41 published measurements as ``{NAME: value}``."""

        if self._last_measurements is None:
            raise RuntimeError(
                "TEPSimulator.reset() must be called before get_measurements()."
            )

        return {
            name.upper(): float(value)
            for name, value in zip(self._measurement_names, self._last_measurements)
        }

    def get_events(self) -> list[dict[str, Any]]:
        """
        Return recorded events, most-recent-last.

        Includes both ICAB fault-injection bookkeeping (``source="icab"``)
        and real plant trip/shutdown events reported by the kernel
        (``source="simulator"``).
        """

        events = [event.to_dict() for event in self._fault_log]

        if self._last_shutdown.get("terminated"):
            events.append(
                TEPEvent(
                    type="shutdown",
                    source="simulator",
                    time=self._time,
                    data={
                        "code": self._last_shutdown["code"],
                        "message": self._last_shutdown["message"],
                    },
                ).to_dict()
            )

        return events

    # -- introspection ----------------------------------------------------

    @property
    def time(self) -> float:
        """Simulated process time in hours since the last reset."""
        return self._time

    @property
    def terminated(self) -> bool:
        """Whether the plant has tripped (shut down) since the last reset."""
        return bool(self._last_shutdown.get("terminated", False))

    @property
    def epoch(self) -> datetime:
        """The wall-clock instant `time == 0.0` (the last reset) corresponds to."""
        return self._epoch

    def available_measurements(self) -> tuple[str, ...]:
        return self._measurement_names

    def available_manipulated_variables(self) -> tuple[str, ...]:
        return self._manipulated_variable_names

    def available_disturbances(self) -> tuple[str, ...]:
        return self._disturbance_names

    # -- internal ----------------------------------------------------------

    def _build_state(self) -> TEPProcessState:
        operating_state = "SHUTDOWN" if self.terminated else "NORMAL"
        timestamp = self._epoch + timedelta(hours=self._time)

        values = {
            name.upper(): float(value)
            for name, value in zip(self._measurement_names, self._last_measurements)
        }

        return TEPProcessState(
            timestamp=timestamp,
            operating_state=operating_state,
            values=values,
        )
