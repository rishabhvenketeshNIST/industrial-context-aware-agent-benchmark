from fastapi import FastAPI, Query

from icab.common.config import get_settings
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.i3x.client import I3XClient
from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.mqtt.client import MQTTClient
from icab.context.opcua import OPCUAClient
from icab.context.uns.models import UNSNode
from icab.context.uns.repository import InMemoryUNSRepository
from icab.context.uns.service import UNSService
from icab.context.uns.tep_builder import build_real_uns_nodes
from icab.gateway.schemas import (
    BrowseMQTTRequest,
    BrowseMQTTResponse,
    BrowseUNSRequest,
    BrowseUNSResponse,
    GetCurrentValueRequest,
    GetCurrentValueResponse,
    GetEntityRelationshipsRequest,
    GetEntityRelationshipsResponse,
    GetHistoricalValuesRequest,
    GetHistoricalValuesResponse,
    I3XGetHistoryResponse,
    I3XGetInfoResponse,
    I3XGetNamespacesResponse,
    I3XGetObjectResponse,
    I3XGetObjectsResponse,
    I3XGetObjectTypesResponse,
    I3XGetRelatedObjectsResponse,
    I3XGetValueResponse,
    OPCUABrowseRequest,
    OPCUAReadRequest,
    ReadMQTTRequest,
    ReadMQTTResponse,
)
from icab.gateway.tools import GatewayTools
from icab.trace.collector import TraceCollector

settings = get_settings()

try:
    # I3XClient connects eagerly (unlike historian/knowledge_graph, which
    # connect lazily per call), so a private i3X server that isn't running
    # yet must not take down the whole gateway process -- every i3x_get_*
    # tool degrades to a clear RuntimeError via GatewayTools._require_i3x
    # instead. See docs/architecture/i3x-private-server.md.
    i3x: I3XClient | None = I3XClient(settings.i3x_base_url)
except Exception as error:  # noqa: BLE001 -- deliberately broad: any connection failure
    print(f"Warning: could not connect to i3X at {settings.i3x_base_url}: {error}")
    i3x = None

# Matches icab.context.opcua.tep_server.TEPOPCUAServer's own default
# endpoint (the real, TEP-backed server -- see docs/architecture/
# context-architecture.md) and the opcua_tep compose service's port
# mapping (4841:4841). Pre-M13-A this pointed at the port/path of an
# earlier, no-longer-running static demo OPC UA server.
opcua = OPCUAClient("opc.tcp://127.0.0.1:4841/icab/tep/")

mqtt = MQTTClient(settings.mqtt_host, settings.mqtt_port)

historian = HistorianService(PostgresHistorianRepository(settings.database_url))

knowledge_graph_repository = Neo4jKnowledgeGraphRepository(
    uri=settings.neo4j_uri,
    username=settings.neo4j_username,
    password=settings.neo4j_password,
)

knowledge_graph = KnowledgeGraphService(knowledge_graph_repository)

trace_collector = TraceCollector()

#: The legacy hand-built prototype tree (path prefix "site/tep/reaction/...")
#: is kept for backward compatibility with the static prototype scenario;
#: `build_real_uns_nodes()` adds the full real-simulator equipment/
#: measurement tree (path prefix "site/tep/<equipment>/...") alongside it.
#: Both trees' "site/tep" root node is identical, so merging them is safe.
uns_repository = InMemoryUNSRepository(
    [
        UNSNode(
            path="site/tep",
            display_name="Tennessee Eastman Process",
            node_type="site",
            canonical_id="urn:icab:site:tep",
        ),
        UNSNode(
            path="site/tep/reaction",
            display_name="Reaction",
            node_type="area",
            canonical_id="urn:icab:area:reaction",
        ),
        UNSNode(
            path="site/tep/reaction/reactor",
            display_name="Reactor",
            node_type="equipment",
            canonical_id="urn:icab:equipment:reactor",
        ),
        UNSNode(
            path="site/tep/reaction/reactor/pressure",
            display_name="Reactor Pressure",
            node_type="measurement",
            canonical_id="urn:icab:measurement:tep_pv_reactor_pressure",
        ),
        UNSNode(
            path="site/tep/reaction/reactor/temperature",
            display_name="Reactor Temperature",
            node_type="measurement",
            canonical_id="urn:icab:measurement:tep_pv_reactor_temperature",
        ),
        UNSNode(
            path="site/tep/reaction/reactor/level",
            display_name="Reactor Level",
            node_type="measurement",
            canonical_id="urn:icab:measurement:tep_pv_reactor_level",
        ),
        *build_real_uns_nodes(),
    ]
)
uns_service = UNSService(uns_repository)

tools = GatewayTools(
    historian=historian,
    knowledge_graph=knowledge_graph,
    uns=uns_service,
    i3x=i3x,
    trace_collector=trace_collector,
    opcua=opcua,
    mqtt=mqtt,
)

app = FastAPI(
    title="ICAB Agent Gateway",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/tools/get_current_value",
    response_model=GetCurrentValueResponse,
)
def get_current_value(request: GetCurrentValueRequest) -> GetCurrentValueResponse:
    return tools.get_current_value(request)


@app.post(
    "/tools/get_historical_values",
    response_model=GetHistoricalValuesResponse,
)
def get_historical_values(
    request: GetHistoricalValuesRequest,
) -> GetHistoricalValuesResponse:
    return tools.get_historical_values(request)


@app.post(
    "/tools/get_entity_relationships",
    response_model=GetEntityRelationshipsResponse,
)
def get_entity_relationships(
    request: GetEntityRelationshipsRequest,
) -> GetEntityRelationshipsResponse:
    return tools.get_entity_relationships(request)


@app.post(
    "/tools/browse_uns",
    response_model=BrowseUNSResponse,
)
def browse_uns(request: BrowseUNSRequest) -> BrowseUNSResponse:
    return tools.browse_uns(request)


@app.get(
    "/tools/i3x_get_info",
    response_model=I3XGetInfoResponse,
)
def i3x_get_info() -> I3XGetInfoResponse:
    return tools.i3x_get_info()


@app.get(
    "/tools/i3x_get_namespaces",
    response_model=I3XGetNamespacesResponse,
)
def i3x_get_namespaces() -> I3XGetNamespacesResponse:
    return tools.i3x_get_namespaces()


@app.get(
    "/tools/i3x_get_object_types",
    response_model=I3XGetObjectTypesResponse,
)
def i3x_get_object_types(
    namespace_uri: str | None = None,
) -> I3XGetObjectTypesResponse:
    return tools.i3x_get_object_types(namespace_uri=namespace_uri)


@app.get(
    "/tools/i3x_get_objects",
    response_model=I3XGetObjectsResponse,
)
def i3x_get_objects(
    type_element_id: str | None = None,
) -> I3XGetObjectsResponse:
    return tools.i3x_get_objects(
        type_element_id=type_element_id,
    )


@app.get(
    "/tools/i3x_get_object",
    response_model=I3XGetObjectResponse,
)
def i3x_get_object(
    element_id: str,
) -> I3XGetObjectResponse:
    return tools.i3x_get_object(
        element_id=element_id,
    )


@app.get(
    "/tools/i3x_get_related_objects",
    response_model=I3XGetRelatedObjectsResponse,
)
def i3x_get_related_objects(
    element_ids: list[str] = Query(...),
    relationship_type: str | None = None,
) -> I3XGetRelatedObjectsResponse:
    return tools.i3x_get_related_objects(
        element_ids=element_ids,
        relationship_type=relationship_type,
    )


@app.get(
    "/tools/i3x_get_value",
    response_model=I3XGetValueResponse,
)
def i3x_get_value(
    element_id: str,
    max_depth: int = 1,
) -> I3XGetValueResponse:
    return tools.i3x_get_value(
        element_id=element_id,
        max_depth=max_depth,
    )


@app.get(
    "/tools/i3x_get_history",
    response_model=I3XGetHistoryResponse,
)
def i3x_get_history(
    element_id: str,
    start_time: str,
    end_time: str,
    max_depth: int = 1,
) -> I3XGetHistoryResponse:
    return tools.i3x_get_history(
        element_id=element_id,
        start_time=start_time,
        end_time=end_time,
        max_depth=max_depth,
    )


@app.post("/tools/opcua_browse")
async def opcua_browse(request: OPCUABrowseRequest):
    return await tools.opcua_browse(request.node_id)


@app.post("/tools/opcua_read")
async def opcua_read(request: OPCUAReadRequest):
    return await tools.opcua_read(request.node_id)


@app.post(
    "/tools/browse_mqtt",
    response_model=BrowseMQTTResponse,
)
def browse_mqtt(request: BrowseMQTTRequest) -> BrowseMQTTResponse:
    return tools.browse_mqtt(request)


@app.post(
    "/tools/read_mqtt",
    response_model=ReadMQTTResponse,
)
def read_mqtt(request: ReadMQTTRequest) -> ReadMQTTResponse:
    return tools.read_mqtt(request)
