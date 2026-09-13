import pytest

from icab.agent.interface import Agent, EvidenceReference, InvestigationResult


def test_agent_is_abstract():
    with pytest.raises(TypeError):
        Agent()


def test_investigation_result_has_normalized_context():
    result = InvestigationResult(
        objective="Investigate the reactor.",
        conclusion="Reactor context acquired.",
    )

    assert result.context.assets == []
    assert result.context.measurements == []
    assert result.context.relationships == []
    assert result.context.provenance == []


def test_normalized_context_accepts_provenance():
    evidence = EvidenceReference(
        source="opcua",
        identifier="ns=2;i=1",
    )

    result = InvestigationResult(
        objective="Investigate the reactor.",
        conclusion="Reactor context acquired.",
        context={
            "assets": [{"id": "reactor-001"}],
            "measurements": [{"id": "pressure-001", "value": 2834.0}],
            "relationships": [],
            "provenance": [evidence],
        },
    )

    assert result.context.assets[0]["id"] == "reactor-001"
    assert result.context.measurements[0]["value"] == 2834.0
    assert result.context.provenance[0].source == "opcua"