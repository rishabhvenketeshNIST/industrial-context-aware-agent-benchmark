# ICAB — Industrial Context-Aware Agent Benchmark

ICAB is a research benchmark for studying how the **context architecture** exposed
to an LLM agent affects its ability to investigate and reason about an industrial
process. The same investigation task is run against a simulated process through
several different context-delivery architectures — a Unified Namespace (UNS), raw
OPC UA, an i3X/CIM-style semantic API, and a graph database — so that agent
performance can be compared across architectures rather than across models.

> **Status:** early-stage / prototype. The core data model, gateway, and a first
> agent architecture comparison are implemented and tested; many benchmark
> configs and docs under [`configs/`](configs/) and [`docs/`](docs/) are
> placeholders for planned work (see [Project status](#project-status)).

## Why

Industrial agents don't fail because the underlying model is weak — they fail
because the process context they need (what is this sensor part of, what is its
current value, what is upstream of it, what state is the plant in) is scattered
across historians, SCADA/OPC UA servers, knowledge graphs, and paper procedures,
each with a different access pattern. ICAB fixes the process, the task, and the
agent logic, and varies only *how context is structured and retrieved*, to
measure the effect of context architecture on investigation quality, tool-call
efficiency, and context reuse.

## How it works

```
                 ┌─────────────────────────┐
  TEP scenario → │   Agent Gateway (FastAPI)│ ← Agent (HTTP tool calls)
  (YAML)         │  src/icab/gateway/       │
                 └───────────┬─────────────┘
                              │
        ┌──────────┬─────────┼─────────┬───────────┐
        ▼          ▼         ▼         ▼           ▼
     Historian   Knowledge   UNS      i3X        OPC UA
    (Timescale/  Graph     (in-mem   client    client (asyncua)
     Postgres)   (Neo4j)   tree)    (HTTP)
```

1. A **TEP scenario** (`configs/prototype/scenarios/*.yaml`) defines a
   deterministic snapshot of the Tennessee Eastman Process — an operating state,
   a timestamp, and a set of measurement values.
2. `TEPAdapter` (`src/icab/tep/`) turns that scenario into an `Environment` of
   canonical entities and observations (`src/icab/cim/`), which an
   `EnvironmentLoader` writes into the historian and knowledge graph.
3. The **Agent Gateway** (`src/icab/gateway/app.py`) exposes that context over
   HTTP as a fixed set of tools: `get_current_value`, `get_historical_values`,
   `get_entity_relationships`, `browse_uns`, the `i3x_get_*` family, and
   `opcua_browse` / `opcua_read`.
4. An **agent** (`src/icab/agent/`) calls those tools through
   `AgentGatewayClient` to answer an investigation objective (e.g. "investigate
   the current reactor operating condition"), producing an `InvestigationResult`
   with findings, normalized context, and evidence references.
5. Every tool call is recorded by a `TraceCollector` into an `InvestigationTrace`
   (`src/icab/trace/`), capturing which context was acquired vs. consumed at each
   step — the raw material for comparing architectures.
6. An `InvestigationEvaluator` (`src/icab/evaluation/`) scores a result against
   an `InvestigationCase`'s required evidence, and
   `ArchitectureComparisonRunner` (`src/icab/experiments/`) runs the *same* case
   through the *same* agent logic across multiple architectures (UNS, OPC UA,
   i3X, knowledge graph) to produce comparable metrics.

### Canonical Information Model (CIM)

`src/icab/cim/` defines an ISA-95-aligned entity hierarchy (Enterprise → Site →
Area → WorkCenter → ProcessCell → Equipment) extended with process/context
entities ICAB needs for investigation: `Measurement`, `ProcessVariable`,
`ControlLoop`, `Alarm`, `OperatingState`, `Fault`, `Event`, `Procedure`,
`Document`. JSON Schemas for entities, observations, and relationships live in
`src/icab/cim/schemas/`.

### Agents

| Agent | Location | Behavior |
|---|---|---|
| `StructuredRetrievalAgent` | `agent/baseline/structured_retrieval.py` | Minimal deterministic baseline: reads one measurement + one relationship set directly by ID. |
| `ContextAwareAgent` | `agent/context_aware.py` | Discovers reactor measurements by browsing the UNS, then reads each one's current value. |
| `ArchitectureAwareAgent` | `agent/architecture_aware.py` | Same investigation logic, parameterized by architecture (`uns`, `opcua`, `i3x`, `kg`) — the workhorse for architecture comparison experiments. |

## Repository layout

```
src/icab/
  agent/            Agent interface + implementations, gateway HTTP client
  cim/              Canonical Information Model (entities, observations, relationships, JSON Schemas)
  common/           Shared settings (pydantic-settings, .env-driven)
  context/          Context sources: historian, knowledge_graph, uns, i3x, opcua + normalizer
  evaluation/       Investigation cases and scoring
  experiments/       Cross-architecture comparison runner
  gateway/          FastAPI app exposing context sources as agent tools
  tasks/            Investigation task models
  tep/              Tennessee Eastman Process state/scenario/adapter
  trace/            Trace event models, collector, JSONL storage

configs/
  prototype/        Working prototype scenario + experiment config
  benchmark/         Versioned benchmark definitions (placeholder)
  experiments/       Ablation/comparison experiment configs (placeholder)

docs/               Architecture, benchmark, and research docs (placeholder)
scripts/            Runnable entry points (see below)
services/           Per-component Dockerfiles (gateway, historian, knowledge_graph, tep)
tests/              Unit, integration, and benchmark test suites
results/            Recorded investigation traces
```

## Getting started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (the project is managed via `pyproject.toml` + `uv.lock`)
- Docker, for the historian (TimescaleDB) and knowledge graph (Neo4j)

### Setup

```bash
# Install dependencies (including dev group)
uv sync

# Configure environment
cp .env.example .env
# edit .env if you change ports/credentials

# Start the historian and knowledge graph
docker compose up -d
```

`.env` / `src/icab/common/config.py` expects:

| Variable | Purpose |
|---|---|
| `ICAB_DATABASE_URL` | Postgres/TimescaleDB connection string for the historian |
| `ICAB_NEO4J_URI` | Bolt URI for the knowledge graph |
| `ICAB_NEO4J_USERNAME` | Neo4j username |
| `ICAB_NEO4J_PASSWORD` | Neo4j password |

### Run the agent gateway

```bash
uv run uvicorn icab.gateway.app:app --reload
```

This serves the tool API (`/tools/...`) that agents call, plus `GET /health`.

### Run a prototype investigation

```bash
uv run python scripts/run_context_aware_agent.py
```

Loads the `normal_001` TEP scenario, seeds the historian/knowledge graph, runs
`ContextAwareAgent` against the gateway, prints the `InvestigationResult`, and
writes a trace to `results/prototype/context_aware_trace.json`.

Other scripts in [`scripts/`](scripts/):

- `run_agent.py` — run an agent against the gateway
- `run_opcua_demo_server.py` — start a local OPC UA server for testing the OPC UA architecture
- `test_opcua_client.py` — smoke-test the OPC UA client against that server
- `load_scenario.py` — load a TEP scenario into the historian/knowledge graph

## Testing

```bash
uv run pytest
```

- `tests/unit/` — pure unit tests, no external services required.
- `tests/integration/` — require the historian/knowledge graph from
  `docker compose up -d` (Postgres/TimescaleDB, Neo4j).

## Project status

Implemented and under test:

- CIM entities/observations/relationships and JSON Schemas
- Historian (TimescaleDB), knowledge graph (Neo4j), UNS, i3X, and OPC UA context
  sources, unified behind the Agent Gateway
- A real, closed-loop Tennessee Eastman Process simulator
  (`icab.tep.simulator.TEPSimulator`, wrapping the `tep-studio` Downs & Vogel
  kernel) alongside the original static prototype scenario path — see
  [`docs/architecture/tep-simulator.md`](docs/architecture/tep-simulator.md)
- `StructuredRetrievalAgent`, `ContextAwareAgent`, `ArchitectureAwareAgent`
- Trace collection/storage and a first-cut investigation evaluator
- `ArchitectureComparisonRunner` for running one case across architectures

Not yet filled in (present as empty placeholders to reserve the intended
structure):

- MQTT as a context/data source (Phase 2 of the ongoing benchmark buildout)
- `docs/benchmark/`, `docs/research/` — design docs
- `configs/benchmark/`, `configs/experiments/`, `configs/prototype/budget.yaml`,
  `configs/prototype/environment.yaml` — versioned benchmark and experiment
  definitions beyond the single `normal_001` prototype scenario
- `LICENSE`, `Makefile`

## License

Not yet finalized — see [`LICENSE`](LICENSE).
