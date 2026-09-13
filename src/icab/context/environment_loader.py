from icab.cim import CIMEnvironment
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.service import KnowledgeGraphService


class EnvironmentLoader:
    """
    Loads a CIM environment into the prototype context backends.
    """

    def __init__(
        self,
        historian: HistorianService,
        knowledge_graph: KnowledgeGraphService,
    ) -> None:
        self.historian = historian
        self.knowledge_graph = knowledge_graph

    def load(self, environment: CIMEnvironment) -> None:
        """
        Persist the complete CIM environment into the appropriate
        context backends.
        """

        self.knowledge_graph.write_entities(environment.entities)

        self.knowledge_graph.write_relationships(environment.relationships)

        self.historian.write_observations(environment.observations)
