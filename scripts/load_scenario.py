from pathlib import Path

from icab.common.config import get_settings
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import (
    Neo4jKnowledgeGraphRepository,
)
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.tep.adapter import TEPAdapter
from icab.tep.scenarios import load_scenario

# DATABASE_URL = "postgresql://icab:icab@localhost:5432/icab"

# NEO4J_URI = "bolt://localhost:7687"
# NEO4J_USERNAME = "neo4j"
# NEO4J_PASSWORD = "icabpassword"


def main() -> None:
    settings = get_settings()
    scenario_path = Path("configs/prototype/scenarios/normal_001.yaml")

    scenario = load_scenario(scenario_path)
    state = scenario.to_process_state()

    adapter = TEPAdapter()

    environment = adapter.build_environment(state)

    historian = HistorianService(PostgresHistorianRepository(settings.database_url))

    knowledge_graph_repository = Neo4jKnowledgeGraphRepository(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
    )

    knowledge_graph = KnowledgeGraphService(knowledge_graph_repository)

    loader = EnvironmentLoader(
        historian=historian,
        knowledge_graph=knowledge_graph,
    )

    try:
        loader.load(environment)
    finally:
        knowledge_graph_repository.close()

    print(
        f"Loaded scenario '{scenario.scenario_id}': "
        f"{len(environment.entities)} entities, "
        f"{len(environment.relationships)} relationships, "
        f"{len(environment.observations)} observations."
    )


if __name__ == "__main__":
    main()
