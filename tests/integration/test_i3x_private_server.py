"""
Integration test for the private i3X milestone:

    TEP data -> private i3X (i3xua wrapping icab.context.opcua.TEPOPCUAServer)
             -> i3X client (icab.context.i3x.client.I3XClient)
             -> ICAB Gateway (icab.gateway.tools.GatewayTools)
             -> agent-accessible observation

Requires `docker compose up -d opcua_tep i3x_server` (see
docs/architecture/i3x-private-server.md). Talks only to ICAB's own private
instance (http://localhost:8090 by default) -- never to the public
https://api.i3x.dev/v1 conformance server.
"""

import time

from icab.common.config import get_settings
from icab.context.historian.repository import InMemoryHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.i3x.client import I3XClient
from icab.context.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.opcua.client import OPCUAClient
from icab.context.uns.repository import InMemoryUNSRepository
from icab.context.uns.service import UNSService
from icab.gateway.tools import GatewayTools

I3X_BASE_URL = "http://localhost:8090"


def _gateway_tools_with_real_i3x() -> GatewayTools:
    return GatewayTools(
        historian=HistorianService(InMemoryHistorianRepository()),
        knowledge_graph=KnowledgeGraphService(InMemoryKnowledgeGraphRepository()),
        uns=UNSService(InMemoryUNSRepository()),
        opcua=OPCUAClient("opc.tcp://127.0.0.1:4840/icab/"),  # unused by this test
        i3x=I3XClient(I3X_BASE_URL),
    )


def test_private_i3x_is_used_by_default_settings():
    settings = get_settings()
    assert settings.i3x_base_url != "https://api.i3x.dev/v1"


def test_private_i3x_server_info_identifies_the_wrapper_not_the_public_server():
    client = I3XClient(I3X_BASE_URL)
    info = client.get_info()

    assert info.spec_version == "1.0"
    assert info.server_name == "i3xua"


def test_gateway_discovers_real_tep_equipment_through_private_i3x():
    tools = _gateway_tools_with_real_i3x()

    response = tools.i3x_get_objects()
    display_names = {obj["display_name"] for obj in response.objects}

    # These are ICAB's own TEP equipment objects (icab.tep.measurements.
    # REAL_TEP_EQUIPMENT), mirrored from icab.context.opcua.TEPOPCUAServer's
    # address space -- not the public server's unrelated pump/tank demo data.
    for name in ("Reactor", "Separator", "Stripper", "Compressor"):
        assert name in display_names


def test_gateway_reads_a_real_tep_measurement_value_through_private_i3x():
    tools = _gateway_tools_with_real_i3x()

    objects = tools.i3x_get_objects().objects
    reactor = next(obj for obj in objects if obj["display_name"] == "Reactor")

    related = tools.i3x_get_related_objects(element_ids=[reactor["element_id"]])
    pressure_object = next(
        item["object"]
        for item in related.related_objects
        if "pressure" in item["object"]["display_name"].lower()
    )

    response = tools.i3x_get_value(element_id=pressure_object["element_id"])

    # A real, plausible TEP reactor-pressure value (nominal ~2705 kPa gauge),
    # not a fabricated placeholder.
    assert 2000.0 < response.value < 3200.0
    assert response.quality is not None


def test_private_tep_backed_i3x_value_changes_over_time():
    """Proves this is a live, moving process -- not a static snapshot."""

    tools = _gateway_tools_with_real_i3x()

    objects = tools.i3x_get_objects().objects
    reactor = next(obj for obj in objects if obj["display_name"] == "Reactor")
    related = tools.i3x_get_related_objects(element_ids=[reactor["element_id"]])
    pressure_object = next(
        item["object"]
        for item in related.related_objects
        if item["object"]["display_name"].lower() == "reactor pressure"
    )

    first = tools.i3x_get_value(element_id=pressure_object["element_id"]).value
    time.sleep(3.0)
    second = tools.i3x_get_value(element_id=pressure_object["element_id"]).value

    assert first != second
