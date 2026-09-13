from datetime import UTC, datetime
from pathlib import Path
from pprint import pprint

from icab.agent.client import AgentGatewayClient
from icab.agent.context_aware import ContextAwareAgent
from icab.common.config import get_settings
from icab.context.environment_loader import EnvironmentLoader
from icab.context.historian.repository import PostgresHistorianRepository
from icab.context.historian.service import HistorianService
from icab.context.knowledge_graph.repository import (
    Neo4jKnowledgeGraphRepository,
)
from icab.context.knowledge_graph.service import KnowledgeGraphService
from icab.tasks.models import InvestigationTask
from icab.tep.adapter import TEPAdapter
from icab.tep.scenarios import ScenarioRegistry
from icab.trace.collector import TraceCollector
from icab.trace.models import InvestigationTrace
from icab.trace.storage import JsonlTraceStorage


def main() -> None:
    scenario_registry = ScenarioRegistry("configs/prototype/scenarios")
    scenario = scenario_registry.get("normal_001")

    settings = get_settings()

    state = scenario.to_process_state()
    environment = TEPAdapter().build_environment(state)

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

    loader.load(environment)

    task = InvestigationTask(
        task_id="prototype-001",
        objective=("Investigate the current reactor operating condition."),
        scenario_id=scenario.scenario_id,
        initial_state={
            "site": "Tennessee Eastman Process",
            "operating_state": scenario.operating_state,
            "timestamp": scenario.timestamp.isoformat(),
        },
    )

    objective = task.objective

    trace_collector = TraceCollector()

    investigation_trace = InvestigationTrace(
        run_id=task.task_id,
        objective=objective,
        agent="context_aware",
        started_at=datetime.now(UTC),
    )

    client = AgentGatewayClient(
        "http://localhost:8000",
        trace_collector=trace_collector,
    )

    agent = ContextAwareAgent(client)

    try:
        result = agent.run(
            objective=objective,
            initial_state=task.initial_state,
        )

        investigation_trace.events = trace_collector.events()
        investigation_trace.context_acquired = sorted(
            {
                item
                for event in investigation_trace.events
                for item in event.context_acquired
            }
        )
        investigation_trace.context_consumed = sorted(
            {
                item
                for event in investigation_trace.events
                for item in event.context_consumed
            }
        )
        investigation_trace.completed_at = datetime.now(UTC)

        investigation_trace.status = "completed"

    except Exception:
        investigation_trace.events = trace_collector.events()
        investigation_trace.completed_at = datetime.now(UTC)
        investigation_trace.status = "failed"
        raise

    finally:
        knowledge_graph_repository.close()

    trace_path = Path("results/prototype/context_aware_trace.json")

    storage = JsonlTraceStorage()
    storage.write_investigation(
        trace_path,
        investigation_trace,
    )

    print("Investigation result:")
    pprint(result.model_dump(mode="json"))

    print()
    print(f"Trace written to: {trace_path}")
    print(f"Trace events: {len(investigation_trace.events)}")


if __name__ == "__main__":
    main()
