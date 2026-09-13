from icab.agent.interface import EvidenceReference, InvestigationResult
from icab.evaluation.cases import PROTOTYPE_REACTOR_CASE
from icab.evaluation.investigation import InvestigationEvaluator


def test_complete_investigation():
    result = InvestigationResult(
        objective=PROTOTYPE_REACTOR_CASE.objective,
        conclusion="The reactor has pressure, temperature, and level measurements.",
        findings={
            "reactor": "Reactor",
            "pressure": 2834.0,
            "temperature": 120.0,
            "level": 50.0,
        },
        evidence=[
            EvidenceReference(
                source="opcua",
                identifier="ns=2;i=1",
            )
        ],
    )

    score = InvestigationEvaluator().evaluate(
        PROTOTYPE_REACTOR_CASE,
        result,
    )

    assert score["objective_match"] is True
    assert score["complete"] is True
    assert score["evidence_score"] == 1.0


def test_incomplete_investigation():
    result = InvestigationResult(
        objective=PROTOTYPE_REACTOR_CASE.objective,
        conclusion="Only pressure was found.",
        findings={
            "reactor": "Reactor",
            "pressure": 2834.0,
        },
    )

    score = InvestigationEvaluator().evaluate(
        PROTOTYPE_REACTOR_CASE,
        result,
    )

    assert score["objective_match"] is True
    assert score["complete"] is False
    assert score["evidence_score"] == 0.5


def test_normalized_context_score():
    result = InvestigationResult(
        objective=PROTOTYPE_REACTOR_CASE.objective,
        conclusion="Reactor context acquired.",
        context={
            "assets": [
                {
                    "id": "reactor-001",
                    "name": "Reactor",
                }
            ],
            "measurements": [
                {
                    "id": "pressure-001",
                    "name": "Pressure",
                    "value": 2834.0,
                },
                {
                    "id": "temperature-001",
                    "name": "Temperature",
                    "value": 120.0,
                },
                {
                    "id": "level-001",
                    "name": "Level",
                    "value": 50.0,
                },
            ],
        },
    )

    score = InvestigationEvaluator().evaluate(
        PROTOTYPE_REACTOR_CASE,
        result,
    )

    assert score["normalized_context_score"] == 1.0
    assert score["normalized_context_hits"] == {
        "reactor": True,
        "pressure": True,
        "temperature": True,
        "level": True,
    }