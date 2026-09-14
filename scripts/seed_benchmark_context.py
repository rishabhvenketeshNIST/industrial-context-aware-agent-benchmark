"""
Seeds ICAB's CONTROLLED BENCHMARK CONTEXT LAYER (icab.benchmark_context)
into the REAL knowledge_graph + historian -- the Enterprise/Site/Area/
Work-Center hierarchy and KPI catalog the 50-questions-per-level
benchmark milestone needs, written through the EXACT SAME
`icab.context.environment_loader.EnvironmentLoader` real TEP data uses.

Idempotent: every entity/relationship/observation carries a
deterministic canonical id and a deterministic (seeded, versioned)
value, so re-running this script simply re-writes the SAME facts --
never accumulates duplicates, never drifts.

Run this ONCE (or any time you want to make sure the layer is present)
before a `scripts/run_level_benchmark.py --level enterprise` (or
site/work_center) invocation -- it does NOT run automatically as part
of an ordinary scenario preparation (this data is static reference
data, not tied to any one TEP scenario/fault).
"""

from __future__ import annotations

import sys


def main() -> int:
    from icab.benchmark_context import build_benchmark_context_environment
    from icab.common.config import get_settings
    from icab.context.environment_loader import EnvironmentLoader
    from icab.context.historian.repository import PostgresHistorianRepository
    from icab.context.historian.service import HistorianService
    from icab.context.knowledge_graph.repository import Neo4jKnowledgeGraphRepository
    from icab.context.knowledge_graph.service import KnowledgeGraphService

    settings = get_settings()

    historian = HistorianService(PostgresHistorianRepository(settings.database_url))
    kg_repository = Neo4jKnowledgeGraphRepository(uri=settings.neo4j_uri, username=settings.neo4j_username, password=settings.neo4j_password)
    knowledge_graph = KnowledgeGraphService(kg_repository)

    try:
        environment = build_benchmark_context_environment()
        loader = EnvironmentLoader(historian=historian, knowledge_graph=knowledge_graph)
        loader.load(environment)

        print(f"Seeded controlled benchmark context: {len(environment.entities)} entities, "
              f"{len(environment.relationships)} relationships, {len(environment.observations)} observations.")
        print("Tagged source='icab_benchmark_context' -- see src/icab/benchmark_context/data.py.")
    finally:
        kg_repository.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
