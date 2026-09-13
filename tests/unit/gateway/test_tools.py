from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from icab.cim import Observation, Relationship, RelationshipType, Site
from icab.context.historian.repository import InMemoryHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.i3x.client import I3XClient
from icab.context.knowledge_graph.repository import (
    InMemoryKnowledgeGraphRepository,
)
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt.client import MQTTClient
from icab.context.mqtt.models import MQTTMessage
from icab.context.opcua import OPCUAClient
from icab.context.uns.repository import InMemoryUNSRepository
from icab.context.uns.service import UNSService
from icab.gateway.schemas import (
    BrowseMQTTRequest,
    GetCurrentValueRequest,
    GetEntityRelationshipsRequest,
    GetHistoricalValuesRequest,
    ReadMQTTRequest,
)
from icab.gateway.tools import GatewayTools
from icab.trace.collector import TraceCollector


def build_gateway_tools(trace_collector: TraceCollector | None = None) -> GatewayTools:
    return GatewayTools(
        historian=HistorianService(InMemoryHistorianRepository()),
        knowledge_graph=KnowledgeGraphService(InMemoryKnowledgeGraphRepository()),
        uns=UNSService(InMemoryUNSRepository()),
        i3x=Mock(spec=I3XClient),
        opcua=Mock(spec=OPCUAClient),
        mqtt=Mock(spec=MQTTClient),
        trace_collector=trace_collector,
    )


def test_get_current_value():
    tools = build_gateway_tools()

    observation = Observation(
        observation_id="gateway-test-001",
        measurement_id="urn:icab:measurement:reactor-pressure",
        timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
        value=2834.0,
        unit="kPa",
        source="TEP",
    )

    tools.historian.write_observations([observation])

    response = tools.get_current_value(
        GetCurrentValueRequest(measurement_id=observation.measurement_id)
    )

    assert response.observation is not None
    assert response.observation.value == 2834.0


def test_get_current_value_records_trace():
    trace_collector = TraceCollector()
    tools = build_gateway_tools(trace_collector)

    observation = Observation(
        observation_id="gateway-trace-test-001",
        measurement_id="urn:icab:measurement:reactor-pressure",
        timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
        value=2834.0,
        unit="kPa",
        source="TEP",
    )

    tools.historian.write_observations([observation])

    tools.get_current_value(
        GetCurrentValueRequest(measurement_id=observation.measurement_id)
    )

    events = trace_collector.events()

    assert len(events) == 1
    assert events[0].action == "get_current_value"
    assert events[0].tool == "get_current_value"
    assert events[0].arguments["measurement_id"] == observation.measurement_id
    assert events[0].result["observation"]["value"] == 2834.0


def test_get_historical_values():
    tools = build_gateway_tools()

    measurement_id = "urn:icab:measurement:reactor-pressure"
    start = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    observation = Observation(
        observation_id="gateway-test-002",
        measurement_id=measurement_id,
        timestamp=start,
        value=2834.0,
        unit="kPa",
        source="TEP",
    )

    tools.historian.write_observations([observation])

    response = tools.get_historical_values(
        GetHistoricalValuesRequest(
            measurement_id=measurement_id,
            start_time=start,
            end_time=start,
        )
    )

    assert len(response.observations) == 1
    assert response.observations[0].value == 2834.0


def test_get_entity_relationships():
    tools = build_gateway_tools()

    site = Site(
        canonical_id="urn:icab:test:gateway-site",
        name="Gateway Test Site",
    )

    relationship = Relationship(
        subject=site.canonical_id,
        predicate=RelationshipType.ASSOCIATED_WITH,
        object=site.canonical_id,
        source="gateway-test",
    )

    tools.knowledge_graph.write_entities([site])
    tools.knowledge_graph.write_relationships([relationship])

    response = tools.get_entity_relationships(
        GetEntityRelationshipsRequest(canonical_id=site.canonical_id)
    )

    assert len(response.relationships) == 1
    assert response.relationships[0].predicate == RelationshipType.ASSOCIATED_WITH


def test_get_historical_values_records_trace():
    trace_collector = TraceCollector()
    tools = build_gateway_tools(trace_collector)

    measurement_id = "urn:icab:measurement:reactor-pressure"
    timestamp = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    observation = Observation(
        observation_id="gateway-trace-test-002",
        measurement_id=measurement_id,
        timestamp=timestamp,
        value=2834.0,
        unit="kPa",
        source="TEP",
    )

    tools.historian.write_observations([observation])

    tools.get_historical_values(
        GetHistoricalValuesRequest(
            measurement_id=measurement_id,
            start_time=timestamp,
            end_time=timestamp,
        )
    )

    events = trace_collector.events()

    assert len(events) == 1
    assert events[0].action == "get_historical_values"
    assert events[0].tool == "get_historical_values"
    assert events[0].result["observations"][0]["value"] == 2834.0


def test_get_entity_relationships_records_trace():
    trace_collector = TraceCollector()
    tools = build_gateway_tools(trace_collector)

    site = Site(
        canonical_id="urn:icab:test:trace-site",
        name="Trace Test Site",
    )

    relationship = Relationship(
        subject=site.canonical_id,
        predicate=RelationshipType.ASSOCIATED_WITH,
        object=site.canonical_id,
        source="gateway-test",
    )

    tools.knowledge_graph.write_entities([site])
    tools.knowledge_graph.write_relationships([relationship])

    tools.get_entity_relationships(
        GetEntityRelationshipsRequest(canonical_id=site.canonical_id)
    )

    events = trace_collector.events()

    assert len(events) == 1
    assert events[0].action == "get_entity_relationships"
    assert events[0].tool == "get_entity_relationships"
    assert len(events[0].result["relationships"]) == 1


@pytest.mark.asyncio
async def test_opcua_browse():
    tools = build_gateway_tools()

    tools.opcua.browse = AsyncMock(
        return_value=[
            Mock(
                node_id="ns=2;i=1",
                display_name="Reactor",
                node_class="Object",
            )
        ]
    )

    result = await tools.opcua_browse("i=85")

    assert result == {
        "nodes": [
            {
                "node_id": "ns=2;i=1",
                "display_name": "Reactor",
                "node_class": "Object",
            }
        ]
    }

    tools.opcua.browse.assert_awaited_once_with("i=85")


@pytest.mark.asyncio
async def test_opcua_read():
    tools = build_gateway_tools()

    tools.opcua.read = AsyncMock(return_value=2834.0)

    result = await tools.opcua_read("ns=2;i=2")

    assert result == {
        "node_id": "ns=2;i=2",
        "value": 2834.0,
    }

    tools.opcua.read.assert_awaited_once_with("ns=2;i=2")


def test_browse_mqtt():
    tools = build_gateway_tools()

    discovered = [
        MQTTMessage(
            topic="icab/tep/reactor/reactor_pressure",
            timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
            source="tep-simulator",
            value=2705.0,
            unit="kPa gauge",
            canonical_id="urn:icab:measurement:reactor_pressure",
        )
    ]
    tools.mqtt.discover = Mock(return_value=discovered)

    response = tools.browse_mqtt(BrowseMQTTRequest(topic_filter="icab/tep/#"))

    assert response.messages == discovered
    tools.mqtt.discover.assert_called_once_with("icab/tep/#", timeout=1.0)


def test_browse_mqtt_records_trace():
    trace_collector = TraceCollector()
    tools = build_gateway_tools(trace_collector)

    tools.mqtt.discover = Mock(return_value=[])

    tools.browse_mqtt(BrowseMQTTRequest())

    events = trace_collector.events()

    assert len(events) == 1
    assert events[0].action == "browse_mqtt"
    assert events[0].tool == "browse_mqtt"


def test_read_mqtt():
    tools = build_gateway_tools()

    message = MQTTMessage(
        topic="icab/tep/reactor/reactor_pressure",
        timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
        source="tep-simulator",
        value=2705.0,
    )
    tools.mqtt.read = Mock(return_value=message)

    response = tools.read_mqtt(
        ReadMQTTRequest(topic="icab/tep/reactor/reactor_pressure")
    )

    assert response.message == message
    tools.mqtt.read.assert_called_once_with(
        "icab/tep/reactor/reactor_pressure", timeout=1.0
    )


def test_read_mqtt_missing_topic_returns_none():
    tools = build_gateway_tools()

    tools.mqtt.read = Mock(return_value=None)

    response = tools.read_mqtt(ReadMQTTRequest(topic="icab/tep/unknown"))

    assert response.message is None


def test_browse_mqtt_without_configured_client_raises():
    tools = build_gateway_tools()
    tools.mqtt = None

    with pytest.raises(RuntimeError):
        tools.browse_mqtt(BrowseMQTTRequest())
