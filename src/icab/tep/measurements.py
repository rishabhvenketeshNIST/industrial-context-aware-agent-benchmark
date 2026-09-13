from dataclasses import dataclass


@dataclass(frozen=True)
class TEPVariable:
    """A process variable exposed by the TEP prototype."""

    variable_id: str
    name: str
    unit: str
    equipment_id: str

    @property
    def canonical_id(self) -> str:
        """Return the ICAB canonical measurement identifier."""
        return f"urn:icab:measurement:{self.variable_id.lower()}"


TEP_VARIABLES = (
    TEPVariable(
        variable_id="TEP_PV_REACTOR_PRESSURE",
        name="Reactor Pressure",
        unit="kPa",
        equipment_id="urn:icab:equipment:reactor",
    ),
    TEPVariable(
        variable_id="TEP_PV_REACTOR_TEMPERATURE",
        name="Reactor Temperature",
        unit="degC",
        equipment_id="urn:icab:equipment:reactor",
    ),
    TEPVariable(
        variable_id="TEP_PV_REACTOR_LEVEL",
        name="Reactor Level",
        unit="percent",
        equipment_id="urn:icab:equipment:reactor",
    ),
    TEPVariable(
        variable_id="TEP_PV_CONDENSER_TEMPERATURE",
        name="Condenser Temperature",
        unit="degC",
        equipment_id="urn:icab:equipment:condenser",
    ),
)
