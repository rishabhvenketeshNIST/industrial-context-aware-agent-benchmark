from abc import ABC, abstractmethod

from icab.context.uns.models import UNSNode


class UNSRepository(ABC):
    @abstractmethod
    def browse(self, path: str) -> list[UNSNode]:
        raise NotImplementedError

    @abstractmethod
    def read(self, path: str) -> UNSNode | None:
        raise NotImplementedError


class InMemoryUNSRepository(UNSRepository):
    def __init__(self, nodes: list[UNSNode] | None = None):
        self._nodes = {node.path: node for node in (nodes or [])}

    def browse(self, path: str) -> list[UNSNode]:
        prefix = path.rstrip("/") + "/"
        children = []

        for node in self._nodes.values():
            if node.path.startswith(prefix):
                remainder = node.path[len(prefix) :]
                if remainder and "/" not in remainder:
                    children.append(node)

        return sorted(children, key=lambda node: node.path)

    def read(self, path: str) -> UNSNode | None:
        return self._nodes.get(path)
