from icab.agent.interface import (
    EvidenceReference,
    InvestigationResult,
)


def test_investigation_result():
    result = InvestigationResult(
        objective="Investigate reactor condition.",
        conclusion="Reactor pressure is 2834.0 kPa.",
        findings={
            "reactor_pressure_kpa": 2834.0,
        },
        evidence=[
            EvidenceReference(
                source="historian",
                identifier=("urn:icab:measurement:tep_pv_reactor_pressure"),
            )
        ],
    )

    assert result.objective == ("Investigate reactor condition.")
    assert result.findings["reactor_pressure_kpa"] == 2834.0
    assert result.evidence[0].source == "historian"


def test_evidence_reference_rejects_unknown_fields():
    try:
        EvidenceReference(
            source="historian",
            identifier="test",
            unexpected="value",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected unknown field to be rejected")
