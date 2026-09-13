from icab.context.normalizer import ContextNormalizer


def test_normalize_uns():
    result = ContextNormalizer.from_uns(
        nodes={
            "nodes": [
                {
                    "node_type": "measurement",
                    "canonical_id": "urn:icab:measurement:pressure",
                    "display_name": "Pressure",
                }
            ]
        },
        measurements={
            "urn:icab:measurement:pressure": {
                "value": 2834.0,
            }
        },
    )

    assert result.measurements == [
        {
            "id": "urn:icab:measurement:pressure",
            "name": "Pressure",
            "value": 2834.0,
        }
    ]
    assert result.provenance[0].source == "uns"


def test_normalize_opcua():
    result = ContextNormalizer.from_opcua(
        nodes={
            "nodes": [
                {
                    "node_id": "ns=2;i=2",
                    "display_name": "Pressure",
                    "node_class": "Variable",
                }
            ]
        },
        values={
            "ns=2;i=2": {
                "value": 2834.0,
            }
        },
    )

    assert result.measurements[0]["id"] == "ns=2;i=2"
    assert result.measurements[0]["value"] == 2834.0


def test_normalize_i3x():
    result = ContextNormalizer.from_i3x(
        reactor={
            "object": {
                "element_id": "reactor-001",
                "display_name": "Reactor",
            }
        },
        related_objects={
            "related_objects": [
                {
                    "element_id": "pressure-001",
                    "display_name": "Reactor Pressure",
                }
            ]
        },
        values={
            "pressure-001": {
                "value": 2834.0,
            }
        },
    )

    assert result.assets[0]["id"] == "reactor-001"
    assert result.measurements[0]["value"] == 2834.0
    assert result.relationships[0]["object"] == "pressure-001"


def test_normalize_kg():
    result = ContextNormalizer.from_kg(
        relationships={
            "relationships": [
                {
                    "subject": "urn:icab:equipment:reactor",
                    "predicate": "MEASURES",
                    "object": "urn:icab:measurement:pressure",
                }
            ]
        }
    )

    assert result.relationships == [
        {
            "subject": "urn:icab:equipment:reactor",
            "predicate": "MEASURES",
            "object": "urn:icab:measurement:pressure",
        }
    ]