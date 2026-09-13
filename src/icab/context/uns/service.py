from icab.context.uns.models import UNSNode
from icab.context.uns.repository import UNSRepository


class UNSService:
    def __init__(self, repository: UNSRepository):
        self.repository = repository

    def browse(self, path: str) -> list[UNSNode]:
        return self.repository.browse(path)

    def read(self, path: str) -> UNSNode | None:
        return self.repository.read(path)
