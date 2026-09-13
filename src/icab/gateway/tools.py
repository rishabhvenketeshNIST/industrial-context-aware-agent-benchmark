from typing import Any

from icab.context.historian.service import HistorianService
from icab.context.i3x.client import I3XClient
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.context.opcua.client import OPCUAClient
from icab.context.uns.service import UNSService
from icab.gateway.schemas import (
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
)
from icab.trace.collector import TraceCollector


class GatewayTools:
    """
    Tool implementation layer exposed by the ICAB Agent Gateway.
    """

    def __init__(
        self,
        historian: HistorianService,
        knowledge_graph: KnowledgeGraphService,
        uns: UNSService,
        i3x: I3XClient,
        opcua: OPCUAClient,
        trace_collector: TraceCollector | None = None,
    ) -> None:
        self.historian = historian
        self.knowledge_graph = knowledge_graph
        self.uns = uns
        self.i3x = i3x
        self.trace_collector = trace_collector
        self.opcua = opcua

    def get_current_value(
        self,
        request: GetCurrentValueRequest,
    ) -> GetCurrentValueResponse:
        observation = self.historian.get_current_value(request.measurement_id)

        response = GetCurrentValueResponse(observation=observation)

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="get_current_value",
                tool="get_current_value",
                arguments=request.model_dump(mode="json"),
                result=response.model_dump(mode="json"),
            )

        return response

    def get_historical_values(
        self,
        request: GetHistoricalValuesRequest,
    ) -> GetHistoricalValuesResponse:
        observations = self.historian.get_historical_values(
            measurement_id=request.measurement_id,
            start_time=request.start_time,
            end_time=request.end_time,
        )

        response = GetHistoricalValuesResponse(observations=observations)

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="get_historical_values",
                tool="get_historical_values",
                arguments=request.model_dump(mode="json"),
                result=response.model_dump(mode="json"),
            )

        return response

    def get_entity_relationships(
        self,
        request: GetEntityRelationshipsRequest,
    ) -> GetEntityRelationshipsResponse:
        relationships = self.knowledge_graph.get_entity_relationships(
            request.canonical_id
        )

        response = GetEntityRelationshipsResponse(relationships=relationships)

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="get_entity_relationships",
                tool="get_entity_relationships",
                arguments=request.model_dump(mode="json"),
                result=response.model_dump(mode="json"),
            )

        return response

    def browse_uns(
        self,
        request: BrowseUNSRequest,
    ) -> BrowseUNSResponse:
        nodes = self.uns.browse(request.path)

        response = BrowseUNSResponse(nodes=nodes)

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="browse_uns",
                tool="browse_uns",
                arguments=request.model_dump(mode="json"),
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_info(self) -> I3XGetInfoResponse:
        info = self.i3x.get_info()

        response = I3XGetInfoResponse(
            spec_version=info.spec_version,
            server_version=info.server_version,
            server_name=info.server_name,
            capabilities=info.capabilities,
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_info",
                tool="i3x_get_info",
                arguments={},
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_namespaces(self) -> I3XGetNamespacesResponse:
        namespaces = self.i3x.get_namespaces()

        response = I3XGetNamespacesResponse(
            namespaces=[
                {
                    "uri": namespace.uri,
                    "display_name": namespace.display_name,
                }
                for namespace in namespaces
            ]
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_namespaces",
                tool="i3x_get_namespaces",
                arguments={},
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_object_types(
        self,
        namespace_uri: str | None = None,
    ) -> I3XGetObjectTypesResponse:
        object_types = self.i3x.get_object_types(namespace_uri=namespace_uri)

        response = I3XGetObjectTypesResponse(
            object_types=[
                {
                    "element_id": object_type.element_id,
                    "display_name": object_type.display_name,
                    "namespace_uri": object_type.namespace_uri,
                    "source_type_id": object_type.source_type_id,
                    "version": object_type.version,
                    "schema": object_type.schema,
                    "related": object_type.related,
                }
                for object_type in object_types
            ]
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_object_types",
                tool="i3x_get_object_types",
                arguments={"namespace_uri": namespace_uri},
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_objects(
        self,
        type_element_id: str | None = None,
    ) -> I3XGetObjectsResponse:
        objects = self.i3x.get_objects(
            type_element_id=type_element_id,
        )

        response = I3XGetObjectsResponse(
            objects=[
                {
                    "element_id": obj.element_id,
                    "display_name": obj.display_name,
                    "type_element_id": obj.type_element_id,
                    "parent_id": obj.parent_id,
                    "is_composition": obj.is_composition,
                    "is_extended": obj.is_extended,
                    "metadata": obj.metadata,
                }
                for obj in objects
            ]
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_objects",
                tool="i3x_get_objects",
                arguments={"type_element_id": type_element_id},
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_object(
        self,
        element_id: str,
    ) -> I3XGetObjectResponse:
        obj = self.i3x.get_object(
            element_id=element_id,
        )

        response = I3XGetObjectResponse(
            object={
                "element_id": obj.element_id,
                "display_name": obj.display_name,
                "type_element_id": obj.type_element_id,
                "parent_id": obj.parent_id,
                "is_composition": obj.is_composition,
                "is_extended": obj.is_extended,
                "metadata": obj.metadata,
            }
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_object",
                tool="i3x_get_object",
                arguments={"element_id": element_id},
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_related_objects(
        self,
        element_ids: list[str],
        relationship_type: str | None = None,
    ) -> I3XGetRelatedObjectsResponse:
        related_objects = self.i3x.get_related_objects(
            element_ids=element_ids,
            relationship_type=relationship_type,
        )

        response = I3XGetRelatedObjectsResponse(
            related_objects=[
                {
                    "source_relationship": related.source_relationship,
                    "object": {
                        "element_id": related.object.element_id,
                        "display_name": related.object.display_name,
                        "type_element_id": related.object.type_element_id,
                        "parent_id": related.object.parent_id,
                        "is_composition": related.object.is_composition,
                        "is_extended": related.object.is_extended,
                        "metadata": related.object.metadata,
                    },
                }
                for related in related_objects
            ]
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_related_objects",
                tool="i3x_get_related_objects",
                arguments={
                    "element_ids": element_ids,
                    "relationship_type": relationship_type,
                },
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_value(
        self,
        element_id: str,
        max_depth: int = 1,
    ) -> I3XGetValueResponse:
        value = self.i3x.get_value(
            element_id=element_id,
            max_depth=max_depth,
        )

        response = I3XGetValueResponse(
            element_id=value.element_id,
            is_composition=value.is_composition,
            value=value.value,
            quality=value.quality,
            timestamp=value.timestamp,
            components=value.components,
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_value",
                tool="i3x_get_value",
                arguments={
                    "element_id": element_id,
                    "max_depth": max_depth,
                },
                result=response.model_dump(mode="json"),
            )

        return response

    def i3x_get_history(
        self,
        element_id: str,
        start_time: str | None = None,
        end_time: str | None = None,
        max_depth: int = 1,
    ) -> I3XGetHistoryResponse:
        history = self.i3x.get_history(
            element_id=element_id,
            start_time=start_time,
            end_time=end_time,
            max_depth=max_depth,
        )

        response = I3XGetHistoryResponse(
            element_id=history.element_id,
            is_composition=history.is_composition,
            values=history.values,
        )

        if self.trace_collector is not None:
            self.trace_collector.record(
                step=0,
                action="i3x_get_history",
                tool="i3x_get_history",
                arguments={
                    "element_id": element_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "max_depth": max_depth,
                },
                result=response.model_dump(mode="json"),
            )

        return response

    async def opcua_browse(self, node_id: str = "i=85") -> dict[str, Any]:
        nodes = await self.opcua.browse(node_id)

        result = {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "display_name": node.display_name,
                    "node_class": node.node_class,
                }
                for node in nodes
            ]
        }

        return result

    async def opcua_read(self, node_id: str) -> dict[str, Any]:
        value = await self.opcua.read(node_id)

        return {
            "node_id": node_id,
            "value": value,
        }
