from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from icab.tep import TEPProcessState

TIMESTAMP = datetime(
    2026,
    9,
    9,
    12,
    0,
    tzinfo=UTC,
)


def test_process_state():
    state = TEPProcessState(
        timestamp=TIMESTAMP,
        operating_state="NORMAL",
        values={
            "TEP_PV_REACTOR_PRESSURE": 2834.0,
            "TEP_PV_REACTOR_TEMPERATURE": 120.0,
        },
    )

    assert state.operating_state == "NORMAL"
    assert state.values["TEP_PV_REACTOR_PRESSURE"] == 2834.0


def test_process_state_is_immutable():
    state = TEPProcessState(
        timestamp=TIMESTAMP,
        operating_state="NORMAL",
        values={
            "TEP_PV_REACTOR_PRESSURE": 2834.0,
        },
    )

    with pytest.raises(ValidationError):
        state.operating_state = "FAULT"


def test_process_state_requires_timezone():
    with pytest.raises(ValidationError):
        TEPProcessState(
            timestamp=datetime(2026, 9, 9, 12, 0),
            operating_state="NORMAL",
            values={},
        )


def test_process_state_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TEPProcessState(
            timestamp=TIMESTAMP,
            operating_state="NORMAL",
            values={},
            unexpected_field="should_fail",
        )
