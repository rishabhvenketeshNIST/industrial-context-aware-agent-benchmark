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
  TEP simulator/scenario │   Agent Gateway (FastAPI)│ ← Agent (HTTP tool calls)
                        │  src/icab/gateway/       │
                        └───────────┬─────────────┘
                                     │
        ┌──────────┬─────────┬──────┼──────┬───────────┐
        ▼          ▼         ▼      ▼      ▼           ▼
     Historian   Knowledge   UNS   MQTT    i3X        OPC UA
    (Timescale/  Graph     (in-mem (Mosquitto client    client (asyncua)
     Postgres)   (Neo4j)   tree)   /paho)  (HTTP)
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
| `LLMInvestigationAgent` | `agent/llm/agent.py` | Drives a tool-calling LLM (`LLMClient`) through the gateway's tools in a loop until it submits a conclusion. Real provider is configurable (NIST RChat by default); unit tests use a deterministic `MockLLMClient`. See [`docs/architecture/llm-agent.md`](docs/architecture/llm-agent.md). |

## Repository layout

```
src/icab/
  agent/            Agent interface + implementations, gateway HTTP client
  cim/              Canonical Information Model (entities, observations, relationships, JSON Schemas)
  common/           Shared settings (pydantic-settings, .env-driven)
  context/          Context sources: historian, knowledge_graph, uns, i3x, opcua + normalizer
  evaluation/       Investigation scoring (keyword + grounded evaluators, information-flow analysis)
  experiments/       Experiment config/runner/storage, architecture combinations, H1-H5 hypotheses
  gateway/          FastAPI app exposing context sources as agent tools
  reporting/         M12 aggregation, hypothesis reports, plotting -- reads persisted results/ only
  scenarios/         D1-D4 BenchmarkScenario model, YAML registry, ScenarioRunner
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
results/            raw/traces/evaluations/aggregate/hypotheses (M9-M11) + reports/figures (M12)
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

# Start the historian, knowledge graph, MQTT broker, and private i3X stack
docker compose up -d
```

`docker compose up -d` builds two images the first time (`opcua_tep`,
`icab`'s own TEP-backed OPC UA server; `i3x_server`, CESMII's `i3xua`
wrapper pinned to a fixed commit) — see
[`docs/architecture/i3x-private-server.md`](docs/architecture/i3x-private-server.md).

`.env` / `src/icab/common/config.py` expects:

| Variable | Purpose |
|---|---|
| `ICAB_DATABASE_URL` | Postgres/TimescaleDB connection string for the historian |
| `ICAB_NEO4J_URI` | Bolt URI for the knowledge graph |
| `ICAB_NEO4J_USERNAME` | Neo4j username |
| `ICAB_NEO4J_PASSWORD` | Neo4j password |
| `ICAB_MQTT_HOST` | MQTT broker host (optional, defaults to `localhost`) |
| `ICAB_MQTT_PORT` | MQTT broker port (optional, defaults to `1883`) |
| `ICAB_I3X_BASE_URL` | ICAB's private, TEP-backed i3X instance (optional, defaults to `http://localhost:8090`) — **not** the public `api.i3x.dev` conformance server |
| `ICAB_LLM_PROVIDER` | Label for the configured LLM provider (optional, e.g. `nist-rchat`) |
| `ICAB_LLM_BASE_URL` | Base URL of an OpenAI-compatible chat-completions endpoint (optional; required to run `LLMInvestigationAgent` with a real provider) |
| `ICAB_LLM_API_KEY` | API key for that endpoint (optional; **never commit a real value** — `.env.example` only documents the variable name) |
| `ICAB_LLM_MODEL` | Model name to request (optional) |

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

### Run a real experiment (M9)

```bash
uv run python scripts/run_experiment.py \
    --scenario d1_reactor_pressure_reading --architectures historian --agent-type llm

# architecture comparison: same scenario/seed/fault, only tools vary
uv run python scripts/run_experiment.py --compare \
    --scenario d2_reactor_context_combination \
    --architectures historian --architectures historian,knowledge_graph --agent-type llm

# named architecture-combination comparison (M10)
uv run python scripts/run_experiment.py \
    --scenario d4_plant_wide_investigation \
    --combination historian_only --combination kg_historian --combination full \
    --agent-type llm

# hypothesis comparison (M11) -- runs H3's treatment/control combinations
# and writes a HypothesisTestResult to results/hypotheses/
uv run python scripts/run_hypothesis_experiment.py \
    --scenario d4_plant_wide_investigation --hypothesis H3

# aggregation/reporting (M12) -- reads already-persisted runs only, no
# simulator/gateway/LLM calls; writes results/reports/*.{json,md} and
# results/figures/*.png
uv run python scripts/generate_report.py \
    --experiment-id m10-d4-combo-validation-v2 \
    --group-by architecture_combination_key --name my-report \
    --plot-metric conclusion_correctness_score

uv run python scripts/generate_hypothesis_report.py \
    --hypothesis H3 --experiment-id m10-d4-combo-validation-v2 \
    --name my-h3-report --plot
```

Runs any agent (deterministic or LLM) against a real `BenchmarkScenario`
through the real gateway, evaluates the result, and persists everything
under `results/{raw,traces,evaluations,aggregate}/`. See
[`docs/research/experiment-plan.md`](docs/research/experiment-plan.md) for
the full schema, reproducibility notes, and a flagged limitation with the
deterministic baselines against real scenario data.

Other scripts in [`scripts/`](scripts/):

- `run_agent.py` — run an agent against the gateway
- `run_opcua_demo_server.py` — start a small static-value OPC UA demo server
  (backs `test_opcua_client.py` and `ArchitectureAwareAgent`'s OPC UA path)
- `run_tep_opcua_server.py` — the real, TEP-backed OPC UA server (containerized
  as the `opcua_tep` compose service; backs the private i3X instance)
- `test_opcua_client.py` — smoke-test the OPC UA client against that server
- `load_scenario.py` — load a TEP scenario into the historian/knowledge graph

The real-simulator context bridges (`icab.tep.context_sync.TEPContextSync`,
`icab.context.opcua.TEPOPCUAServer`) are exercised directly by
`tests/integration/test_tep_context_sync.py` and
`tests/integration/test_opcua_tep_server.py` — see
[`docs/architecture/context-architecture.md`](docs/architecture/context-architecture.md).
The private i3X stack (`opcua_tep` + `i3x_server` compose services) is
exercised by `tests/integration/test_i3x_private_server.py` — see
[`docs/architecture/i3x-private-server.md`](docs/architecture/i3x-private-server.md).

## Testing

```bash
uv run pytest
```

- `tests/unit/` — pure unit tests, no external services required.
- `tests/integration/` — require the full `docker compose up -d` stack
  (Postgres/TimescaleDB, Neo4j, Mosquitto, and the private
  `opcua_tep`/`i3x_server` pair). The gateway degrades gracefully if the
  private i3X server specifically isn't running (a warning is printed, and
  `i3x_get_*` tool calls raise a clear `RuntimeError`) rather than failing
  to import — so most of `tests/unit/gateway/` still passes without it.
- `tests/integration/test_llm_rchat.py` and
  `tests/integration/test_scenario_llm_end_to_end.py` are additionally
  gated behind `ICAB_RUN_LLM_INTEGRATION_TESTS=1` — they make real,
  metered calls to the configured LLM provider, so they are skipped by
  default even when the rest of `tests/integration/` runs.

## Project status

Implemented and under test:

- CIM entities/observations/relationships and JSON Schemas
- Historian (TimescaleDB), knowledge graph (Neo4j), UNS, i3X, OPC UA, and MQTT
  (Mosquitto) context sources, unified behind the Agent Gateway
- A real, closed-loop Tennessee Eastman Process simulator
  (`icab.tep.simulator.TEPSimulator`, wrapping the `tep-studio` Downs & Vogel
  kernel) alongside the original static prototype scenario path — see
  [`docs/architecture/tep-simulator.md`](docs/architecture/tep-simulator.md)
- MQTT as a first-class context/data source (`icab.context.mqtt`), including
  a `TEPMeasurementPublisher` bridge from the simulator onto an ICAB MQTT
  topic namespace and gateway `browse_mqtt`/`read_mqtt` tools — see
  [`docs/architecture/mqtt.md`](docs/architecture/mqtt.md)
- The real simulator wired into Historian + Knowledge Graph
  (`icab.tep.context_sync.TEPContextSync`), UNS
  (`icab.context.uns.tep_builder`), a real, self-hosted OPC UA server
  mirroring the full measurement set (`icab.context.opcua.TEPOPCUAServer`),
  and a **private, TEP-backed i3X instance** (CESMII's `i3xua` wrapper in
  front of that same OPC UA server) — each architecture deliberately keeps
  its own access pattern rather than exposing an identical view; see
  [`docs/architecture/context-architecture.md`](docs/architecture/context-architecture.md)
  and [`docs/architecture/i3x-private-server.md`](docs/architecture/i3x-private-server.md)
  (the public `api.i3x.dev` conformance server stays read-only/unused, by design)
- `StructuredRetrievalAgent`, `ContextAwareAgent`, `ArchitectureAwareAgent`
  (deterministic baselines) and `LLMInvestigationAgent` (real tool-calling
  LLM agent, provider-configurable, NIST RChat by default) — see
  [`docs/architecture/llm-agent.md`](docs/architecture/llm-agent.md)
- Trace collection/storage, the original keyword-matching investigation
  evaluator (`icab.evaluation.investigation.InvestigationEvaluator`,
  unchanged), and a stronger, fully deterministic, structured evaluator
  (`icab.evaluation.grounded.GroundedInvestigationEvaluator`) scoring
  required evidence, evidence provenance, canonical-id validity, temporal
  and relationship evidence, causal-reasoning/conclusion-correctness
  heuristics, unsupported numeric claims, acquired-vs-consumed context, and
  investigation completeness against a `BenchmarkScenario`'s ground truth —
  deliberately not an LLM-as-judge; see
  [`docs/benchmark/evaluation.md`](docs/benchmark/evaluation.md)
- `ArchitectureComparisonRunner` for running one case across architectures
  (unchanged since before M9 — see `icab.experiments.ExperimentRunner`
  below for the newer, scenario-based path)
- A D1-D4 investigation scenario framework (`icab.scenarios`) driving the
  real simulator over time with deterministic seeds, scheduled faults, and
  structured ground truth, plus one real, empirically-verified scenario per
  difficulty level under `configs/benchmark/scenarios/` — connected
  end-to-end to `LLMInvestigationAgent` and the real gateway/LLM provider;
  see [`docs/benchmark/tasks.md`](docs/benchmark/tasks.md)
- A locally reproducible experiment runner (`icab.experiments.
  ExperimentRunner`, `scripts/run_experiment.py`) that runs any agent
  (deterministic or LLM) against a `BenchmarkScenario`, holding the
  process/seed/objective/model fixed while varying only which
  architectures' tools are exposed — persisted as raw/trace/evaluation/
  aggregate JSON+CSV under `results/`. Every run is tagged `RunValidity`
  (the three pre-M5 deterministic baselines are `legacy_control_only` —
  regression/control use only, excluded from the main benchmark
  comparison by default — since they don't see real scenario data; a new,
  separate `ScenarioAwareBaselineAgent` deterministic baseline does, and is
  benchmark-eligible); a `generation_id` provenance tag on every
  observation/relationship a scenario preparation writes lets the
  evaluator scope relationship evidence to the current run rather than a
  shared historian/knowledge graph's accumulated history. See
  [`docs/research/experiment-plan.md`](docs/research/experiment-plan.md)
- Architecture combinations as a first-class experimental variable (M10):
  eight named, documented tool-availability presets
  (`icab.experiments.architecture_combinations`, `--combination` on
  `scripts/run_experiment.py`) an agent is never told about beyond its own
  tool list; a separate `InformationFlowAnalyzer`
  (`icab.evaluation.information_flow`) that distinguishes discoverability
  (learned a measurement exists) from acquisition (retrieved its value)
  from cross-architecture redundancy (the same value fetched through more
  than one architecture) per run; per-run latency/token-usage totals; and
  a `HeterogeneousControlsError` check in `ExperimentResultStore.
  write_aggregate` that refuses to treat a set of runs as a controlled
  architecture comparison unless their scenario/seed/model/budget actually
  match. See [`docs/research/experiment-plan.md`](docs/research/experiment-plan.md)
- H1-H5 hypothesis-testing infrastructure (M11): `icab.experiments
  .hypotheses` maps each locked hypothesis
  ([`docs/research/hypotheses.md`](docs/research/hypotheses.md)) to a
  specific treatment/control architecture-combination pair and an
  existing evaluator/information-flow metric, and produces a descriptive
  (never inferential -- no significance test, no "proven" claim)
  `HypothesisTestResult`; `scripts/run_hypothesis_experiment.py
  --scenario <id> --hypothesis H<n>` runs it end-to-end. Real validation
  against the live stack (one D4 run per arm) surfaced and fixed two
  evaluator measurement bugs (`tool_call_count` double-counting a new
  M10 trace-event kind; a cited timestamp's year misread as an
  unsupported numeric claim) -- see
  [`docs/research/experiment-plan.md`](docs/research/experiment-plan.md)
- Result aggregation and reporting (M12): `icab.reporting` turns
  persisted `results/{raw,traces,evaluations}/` artifacts into grouped
  summaries (`aggregate_records` -- by scenario, difficulty, architecture
  (combination), agent type, LLM model, or seed/run, with
  mean/median/stdev/min/max/n and success/failure counts per group,
  reusing the same heterogeneous-controls safeguard as M9/M10's
  `write_aggregate`), richer hypothesis reports
  (`build_hypothesis_report` -- per-arm statistics plus data-derived
  `limitations`, never a "proven"/"significant" verdict), and
  reproducible plots (`icab.reporting.plotting`, matplotlib, headless).
  Effectiveness and efficiency metrics are kept in two explicit, separate
  groups rather than one collapsed score
  (`icab.reporting.metrics.EFFECTIVENESS_METRICS`/`EFFICIENCY_METRICS`).
  `scripts/generate_report.py`/`generate_hypothesis_report.py` operate
  entirely on already-persisted runs -- no simulator/gateway/LLM calls --
  and write `results/reports/*.{json,md}` + `results/figures/*.png`. See
  [`docs/research/experiment-plan.md`](docs/research/experiment-plan.md)
- Complete TEP process-context model and knowledge graph (M13-A): all 53
  real TEP process variables (41 measurements + 12 manipulated
  variables/actuators, verified against `tep_studio` directly rather than
  assumed) now have a canonical identity, required metadata (unit,
  equipment location, a unit-derived physical-quantity `category`,
  source/provenance), and are synchronized into the knowledge graph.
  Beyond the pre-existing `PART_OF`/`MONITORS` hierarchy, the KG now
  represents `ACTUATES` (equipment -> actuator, structural),
  `CONTROLS` (actuator -> measurement, sourced from the real
  decentralized controller's own control-loop registry,
  `tep_studio.control.registry.RICKER_MODE1`), and `HAS_LIMIT`/
  `ASSOCIATED_WITH` (the two documented Mode-1 constraint overrides) --
  every nontrivial relationship traceable to a specific, citable source,
  no causal/diagnostic edges invented. See
  [`docs/architecture/tep-context-model.md`](docs/architecture/tep-context-model.md)

Not yet filled in (present as empty placeholders to reserve the intended
structure):

- `docs/benchmark/specification.md`,
  `docs/benchmark/splits.md` — design docs
- `configs/experiments/`, `configs/prototype/budget.yaml`,
  `configs/prototype/environment.yaml` — versioned experiment definitions
  and a scenario suite broader than one scenario per difficulty level
- `LICENSE`, `Makefile`

## License

Not yet finalized — see [`LICENSE`](LICENSE).
