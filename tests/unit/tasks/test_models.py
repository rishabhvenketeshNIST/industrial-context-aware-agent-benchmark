from icab.tasks.models import InvestigationTask


def test_investigation_task():
    task = InvestigationTask(
        task_id="prototype-001",
        objective="Investigate the current reactor operating condition.",
        scenario_id="normal_001",
        initial_state={
            "site": "Tennessee Eastman Process",
            "operating_state": "NORMAL",
        },
    )

    assert task.task_id == "prototype-001"
    assert task.objective == ("Investigate the current reactor operating condition.")
    assert task.scenario_id == "normal_001"
    assert task.initial_state["operating_state"] == "NORMAL"


def test_investigation_task_rejects_unknown_fields():
    try:
        InvestigationTask(
            task_id="prototype-001",
            objective="Test objective.",
            scenario_id="normal_001",
            unexpected="value",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected unknown field to be rejected")
