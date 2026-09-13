from datetime import UTC, datetime

from icab.context.environment import ArchitectureEnvironment
from icab.tep.state import TEPProcessState


def test_architecture_environment_exposes_common_process_state():
    state = TEPProcessState(
        timestamp=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        operating_state="normal",
        values={
            "TEP_PV_REACTOR_PRESSURE": 2834.0,
            "TEP_PV_REACTOR_TEMPERATURE": 120.0,
            "TEP_PV_REACTOR_LEVEL": 50.0,
            "TEP_PV_CONDENSER_TEMPERATURE": 80.0,
        },
    )

    environment = ArchitectureEnvironment(state=state)

    assert environment.reactor_pressure == 2834.0
    assert environment.reactor_temperature == 120.0
    assert environment.reactor_level == 50.0
    assert environment.condenser_temperature == 80.0
