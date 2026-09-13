from i3x import (
    Client,
    CurrentValue,
    HistoricalValue,
    Namespace,
    ObjectInstance,
    ObjectType,
    RelatedObject,
    ServerInfo,
)


class I3XClient:
    """Thin ICAB wrapper around the official i3X client."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.client = Client(
            base_url=base_url,
            timeout=timeout,
        )
        self.client.connect()

    def get_info(self) -> ServerInfo:
        return self.client.get_info()

    def get_namespaces(self) -> list[Namespace]:
        return self.client.get_namespaces()

    def get_object_types(
        self,
        namespace_uri: str | None = None,
    ) -> list[ObjectType]:
        return self.client.get_object_types(namespace_uri=namespace_uri)

    def get_objects(
        self,
        type_element_id: str | None = None,
        *,
        include_metadata: bool = False,
        root: bool | None = None,
    ) -> list[ObjectInstance]:
        return self.client.get_objects(
            type_element_id=type_element_id,
            include_metadata=include_metadata,
            root=root,
        )

    def get_object(
        self,
        element_id: str,
        *,
        include_metadata: bool = False,
    ) -> ObjectInstance:
        return self.client.get_object(
            element_id=element_id,
            include_metadata=include_metadata,
        )

    def get_related_objects(
        self,
        element_ids: list[str],
        relationship_type: str | None = None,
        *,
        include_metadata: bool = False,
    ) -> list[RelatedObject]:
        return self.client.get_related_objects(
            element_ids=element_ids,
            relationship_type=relationship_type,
            include_metadata=include_metadata,
        )

    def get_value(
        self,
        element_id: str,
        *,
        max_depth: int = 1,
    ) -> CurrentValue:
        return self.client.get_value(
            element_id=element_id,
            max_depth=max_depth,
        )

    def get_history(
        self,
        element_id: str,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        max_depth: int = 1,
    ) -> HistoricalValue:
        return self.client.get_history(
            element_id=element_id,
            start_time=start_time,
            end_time=end_time,
            max_depth=max_depth,
        )
