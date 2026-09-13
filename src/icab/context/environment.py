from dataclasses import dataclass

from icab.tep.state import TEPProcessState


@dataclass(frozen=True)
class ArchitectureEnvironment:
    """Common process state exposed through multiple information architectures."""

    state: TEPProcessState

    @property
    def reactor_pressure(self) -> float:
        return float(self.state.values["TEP_PV_REACTOR_PRESSURE"])

    @property
    def reactor_temperature(self) -> float:
        return float(self.state.values["TEP_PV_REACTOR_TEMPERATURE"])

    @property
    def reactor_level(self) -> float:
        return float(self.state.values["TEP_PV_REACTOR_LEVEL"])

    @property
    def condenser_temperature(self) -> float:
        return float(self.state.values["TEP_PV_CONDENSER_TEMPERATURE"])
