# ICAB — Industrial Context-Aware Agent Benchmark

ICAB is a research benchmark for studying how the **context architecture**
exposed to an LLM agent affects its ability to investigate an industrial
process. A real, closed-loop Tennessee Eastman Process (TEP) simulator drives
a set of investigation tasks; the same task is run against several different
context-delivery architectures (a historian, a knowledge graph, a Unified
Namespace, OPC UA, MQTT, and a private i3X instance) so agent performance can
be compared across architectures rather than across models.

This README is a **user guide** for running the benchmark. For the research
design (locked hypotheses, context dimensions C1-C7, research questions) and
the milestone-by-milestone development history, see
[`docs/research/`](docs/research/) and
[`docs/research/development-history.md`](docs/research/development-history.md).

## What ICAB Does

An agent is given an objective (e.g. "What is the current reactor pressure,
and is it within the normal safe operating range?") and a fixed set of tools
for one or more context architectures. It investigates by calling those
tools, then submits a conclusion. A deterministic evaluator
(`GroundedInvestigationEvaluator` — no LLM-as-judge) scores the result
against hidden ground truth the agent never saw, and every result is
persisted for later analysis. `scripts/run_benchmark.py` runs this whole
pipeline — task selection, TEP simulation, fault injection, agent execution,
evaluation, and reporting — from one command.

## Quick Start

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Docker
(for PostgreSQL/TimescaleDB, Neo4j, MQTT, and the private i3X stack).

```powershell
# 1. Install dependencies
uv sync

# 2. Configure environment
copy .env.example .env
# edit .env if you change ports/credentials -- never commit .env

# 3. Start PostgreSQL/TimescaleDB, Neo4j, MQTT, and the private i3X stack
docker compose up -d

# 4. Start the Agent Gateway (in a separate terminal -- leave it running)
uv run uvicorn icab.gateway.app:app --reload

# 5. Smoke test: one real task, one architecture, one seed, the
#    deterministic baseline agent
uv run python scripts/run_benchmark.py --suite tep-v1 --split development --task d1-qa-current-pressure --agent baseline --architectures historian --seeds 1
```

If the gateway or any required service isn't reachable, the command fails
immediately with an actionable message (which service, and how to start it)
rather than a raw connection error. On success it prints a summary and the
paths to every output it wrote — see
[Understanding the Output](#understanding-the-output).

`docker compose up -d` builds two images the first time (`opcua_tep`,
ICAB's own TEP-backed OPC UA server; `i3x_server`, CESMII's `i3xua` wrapper
pinned to a fixed commit) — see
[`docs/architecture/i3x-private-server.md`](docs/architecture/i3x-private-server.md).

`.env` (see `.env.example` for the full list with placeholders, never real
secrets):

| Variable | Purpose |
|---|---|
| `ICAB_DATABASE_URL` | Postgres/TimescaleDB connection string for the historian |
| `ICAB_NEO4J_URI` / `_USERNAME` / `_PASSWORD` | Neo4j connection |
| `ICAB_MQTT_HOST` / `_PORT` | MQTT broker (optional, defaults to `localhost:1883`) |
| `ICAB_I3X_BASE_URL` | ICAB's private, TEP-backed i3X instance (optional, defaults to `http://localhost:8090`) — **not** the public `api.i3x.dev` conformance server |
| `ICAB_LLM_PROVIDER` / `_BASE_URL` / `_API_KEY` / `_MODEL` | LLM provider config for `--agent llm` (optional unless you run the LLM agent; **never commit a real API key**) |

## Running the Benchmark

All commands below assume the Docker stack and the Agent Gateway (step 3-4
above) are already running.

### Smoke test

```powershell
uv run python scripts/run_benchmark.py --suite tep-v1 --split development --task d1-qa-current-pressure --agent baseline --architectures historian --seeds 1
```

One real task, one architecture, one seed, the fast deterministic baseline
agent — exercises the complete real orchestration path (simulator → context
sync → gateway → agent → evaluator → persistence → reports) in seconds, not
a mocked shortcut.

### Development / Validation / Test splits

```powershell
uv run python scripts/run_benchmark.py --suite tep-v1 --split development --agent llm --architectures all --seeds 1
uv run python scripts/run_benchmark.py --suite tep-v1 --split validation --agent llm --architectures all --seeds 1
uv run python scripts/run_benchmark.py --suite tep-v1 --split test --agent llm --architectures all --seeds 1
```

Runs every task whose scenario is assigned to that split (splits are
scenario-grouped to prevent leakage — see
[`docs/benchmark/splits.md`](docs/benchmark/splits.md)). See
[Research Data Collection](#research-data-collection) for the recommended
order to actually run these in.

### One specific task

```powershell
uv run python scripts/run_benchmark.py --suite tep-v1 --task d1-qa-current-pressure --agent llm --architectures historian --seeds 1
```

### One specific architecture

```powershell
uv run python scripts/run_benchmark.py --suite tep-v1 --split development --agent llm --architectures knowledge_graph --seeds 1
```

`--architectures` also accepts `all` (one arm per architecture the selected
task itself declares available — never a superset) or a named combination
key (e.g. `kg_historian`) — see [Architectures](#architectures).

### Multiple seeds

```powershell
uv run python scripts/run_benchmark.py --suite tep-v1 --agent llm --architectures all --seeds 1,2,3,4,5
```

Each seed overrides the scenario's own seed for that run, producing a
controlled sweep over different simulated trajectories — task, objective,
model, and budgets stay fixed; only the seed (and, separately, the
architecture) varies.

### Multiple repetitions

```powershell
uv run python scripts/run_benchmark.py --suite tep-v1 --task d1-qa-current-pressure --agent llm --architectures historian --seeds 1 --repetitions 3
```

Repeats the exact same (task, architecture, seed) 3 times — useful for
observing run-to-run variance from LLM sampling even at a fixed seed.

Every command above prints a final summary: benchmark ID, suite, split,
task/scenario/architecture/agent/seed/repetition counts, and
total/successful/failed/skipped run counts, plus every output path.

## Understanding the Output

Every invocation writes under `results/` (created automatically; `.gitkeep`
placeholders keep the directory skeleton in git, the generated contents
themselves are gitignored — see `.gitignore` and
[Research Data Collection](#research-data-collection)):

```text
results/raw/            one ExperimentRecord JSON per run (config, metadata, status)
results/traces/         one JSONL trace per run (every tool call, argument, and result)
results/evaluations/    one EvaluationReport JSON per completed run
results/aggregate/      <benchmark_id>.{json,csv} -- cross-run comparison table
results/reports/        <benchmark_id>.{json,md}  -- grouped aggregate report
                        <benchmark_id>-qa.{json,md} -- the researcher QA report (below)
results/figures/        <benchmark_id>-<metric>.png -- effectiveness/efficiency plots
```

**The researcher QA report** (`results/reports/<benchmark_id>-qa.md`) is the
most useful single file for inspecting what actually happened. For every
run, it shows:

- the exact question/objective presented to the agent
- the agent's final answer, verbatim
- the correct answer, rendered as readable prose from the ground truth
  (never a raw object dump)
- required evidence vs. evidence the agent actually provided
- that run's own metrics (`required_evidence_score`, `canonical_id_score`,
  `relationship_score`, `conclusion_correctness_score`, `grounding_score`,
  `completeness_score`, tool-call/context-acquired/context-consumed counts,
  latency, token usage)

followed by an overall summary (run counts, mean/median metrics, and
architecture/difficulty/task-type breakdowns) at the bottom.

**Ground truth is a researcher-only artifact.** The agent is given only its
objective, legitimate initial state, and whatever it retrieves through
tool calls — it never receives `ground_truth`, expected entities/
relationships/evidence, or hidden fault information. The QA report may show
this ground truth (since it's built entirely from already-persisted results,
after the run completed); this is verified directly by test — see
[Tests](#tests).

## Benchmark Configuration

The most commonly used `scripts/run_benchmark.py` flags:

| Flag | Meaning |
|---|---|
| `--suite` | Registered suite (required; currently `tep-v1`) |
| `--split` | `development` / `validation` / `test` (default: every split) |
| `--task` | One explicit task id (overrides `--split`/`--scenario`) |
| `--scenario` | Restrict to tasks against one scenario id |
| `--agent` | `baseline` or `llm` (see [Agents](#agents)) |
| `--architectures` | `all`, a named combination key, or a comma-separated list (see [Architectures](#architectures)) |
| `--seeds` | Comma-separated seed overrides, e.g. `1,2,3,4,5` |
| `--repetitions` | Repeat each (task, architecture, seed) this many times |
| `--llm-model`, `--temperature` | LLM generation config (`--agent llm` only) |
| `--max-steps`, `--max-tool-calls`, `--max-context-tokens`, `--max-wall-time` | Agent budgets (`--agent llm` only; unset = unbounded) |
| `--name` | Benchmark id (default: auto-generated, never collides) |
| `--force` | Allow `--name` to overwrite a benchmark id that already has results |
| `--gateway-url`, `--results-root` | Infrastructure locations |

Run `uv run python scripts/run_benchmark.py --help` for the full, current
list with descriptions.

## Agents

| Agent (`--agent`) | Behavior |
|---|---|
| `baseline` | `ScenarioAwareBaselineAgent` — a fixed, deterministic tool sequence (no LLM). Fast, useful for smoke-testing the pipeline and as a non-LLM control. |
| `llm` | `LLMInvestigationAgent` — a real tool-calling LLM, driven through the Agent Gateway's HTTP API only (never a direct database/broker/simulator connection). Provider-configurable; NIST RChat by default. |

A legacy `DeterministicAgentKind` value (e.g. `structured_retrieval`) is
also accepted as an explicit, separate opt-in for a labeled legacy control
— never the default, and always excluded from normal aggregates.

## Architectures

| Name | What it gives the agent |
|---|---|
| `historian` | Current/historical measurement values (TimescaleDB) |
| `knowledge_graph` | Entity relationships (Neo4j) |
| `uns` | Hierarchical discovery/browsing (in-process Unified Namespace tree) |
| `opcua` | Browse + read against a real, self-hosted OPC UA server |
| `mqtt` | Browse + read over an MQTT topic namespace |
| `i3x` | CESMII i3X semantic API, backed by ICAB's own private, TEP-backed instance |

`--architectures all` expands to one arm per architecture the *selected
task* itself declares available — never a superset, and never an
architecture the task can't actually satisfy. `i3x` is exercised by
`tep-v2` (see below), though not yet by any `tep-v1` task.

## ICAB v2: ISA-95 use cases and context analysis

`--suite tep-v2` runs the SAME `scripts/run_benchmark.py` command against
a broader research question than fault diagnosis alone: what industrial
context is required at each ISA-95 level (`Enterprise`/`Site`/`Area`/
`WorkCenter`/`ProcessCell`/`Equipment`), how should it be represented,
how much is sufficient, and which architectures can provide it? See
[`docs/benchmark/specification-v2.md`](docs/benchmark/specification-v2.md)
for the full concept chain, the 14 real, honestly-scoped
`IndustrialUseCase`s (0 at Enterprise/Site/Work Center — TEP genuinely
has no data there, reported rather than fabricated), the deterministic
127-combination context-dimension generator, and the necessity/
sufficiency/composition/representation/efficiency analysis suites.

```powershell
# Run tep-v2 exactly like tep-v1
uv run python scripts/run_benchmark.py --suite tep-v2 --agent llm --architectures all --seeds 1

# Explore the framework
uv run python scripts/icab_v2_cli.py list-isa95-levels
uv run python scripts/icab_v2_cli.py list-use-cases
uv run python scripts/icab_v2_cli.py list-context-combinations --cardinality 2

# Verify every architecture is actually connected before trusting results
uv run python scripts/check_architecture_health.py

# Analyze already-persisted tep-v2 results for one use case
uv run python scripts/icab_v2_cli.py analyze-sufficiency --use-case eq-value-and-relationship-combination
uv run python scripts/icab_v2_cli.py generate-profiles --out results/reports/context-design-profiles.json
```

Choosing WHICH context conditions to test, systematically, is a separate
layer on top of the above (`docs/benchmark/specification-v2.md`'s
"Experimental design strategies" section): single-dimension, pairwise,
progressive, targeted, and ablation designs, each resolved against a
task's own architectures (`exact`/`overshoot`/`unrealizable` -- most of
the 127-combination space cannot be realized in isolation by ICAB's six
architectures, a real finding reported explicitly rather than hidden).

```powershell
# Dry run -- see how a design strategy resolves for one task, no infrastructure needed
uv run python scripts/icab_v2_cli.py resolve-conditions --task d4plant-investigation-open-ended --design single

# Actually run an ablation campaign against real infrastructure
uv run python scripts/run_context_experiment.py --suite tep-v2 --task d2cooling-diagnosis-heat-transfer-category --design ablation --baseline C3+C5 --allow-overshoot --agent llm --seeds 1

# Cross-use-case analysis outputs (context requirement matrix, architecture x context, failure modes, ISA-95 coverage, candidate MSC table)
uv run python scripts/icab_v2_cli.py matrix-context-requirement
uv run python scripts/icab_v2_cli.py matrix-isa95-coverage
```

The first real empirical campaign run with this machinery — a
5-use-case cohort, 33 real runs, full context-requirement/candidate-MSC/
architecture/failure tables, and an explicit observed-vs-tentative-vs-
unsupported claim audit — is written up in
[`docs/research/context-requirement-campaign-1.md`](docs/research/context-requirement-campaign-1.md),
following the fixed protocol in
[`docs/research/context-requirement-protocol.md`](docs/research/context-requirement-protocol.md).

## ICAB v3: six independent ISA-95-level benchmarks

A further restructuring on top of the above (unchanged): SIX separate
benchmarks (Enterprise/Site/Area/Work Center/Process Cell/Equipment,
`icab.benchmark.levels.LEVEL_BENCHMARKS`), each with its own id,
question bank, and `results/<level>/` tree — running the Equipment
benchmark never touches, mixes with, or contaminates Process Cell or
Area results (enforced, not just conventional: a result whose own
declared level disagrees with where it's about to be saved fails
loudly). Enterprise/Site/Work Center are explicit,
`executable=False` — genuinely no TEP data, never fabricated. See
[`docs/benchmark/specification-v3.md`](docs/benchmark/specification-v3.md)
for the full model (`Question` -> `QuestionInstance` -> `Repetition`,
two repetition modes, macro/micro aggregation, per-level manifests).

```powershell
# See which benchmarks exist and whether each is currently executable
uv run python scripts/icab_v2_cli.py list-benchmarks
uv run python scripts/icab_v2_cli.py list-questions --level equipment

# Start a level's results/ tree clean (dry run by default; --force to actually archive+reset)
uv run python scripts/reset_active_results.py
uv run python scripts/reset_active_results.py --force

# Run a filtered slice of one level's question bank against real infrastructure
uv run python scripts/run_question_benchmark.py --level equipment --question-ids Q-d1-qa-current-pressure --context-combinations C5 --agent llm --repetitions 5

# Question -> use case -> benchmark-level statistics (macro AND micro average, every question's own result preserved)
uv run python scripts/icab_v2_cli.py analyze-question-stats --level equipment --question Q-d1-qa-current-pressure
uv run python scripts/icab_v2_cli.py analyze-benchmark-level-stats --level equipment
```

## Repository Structure

```text
icab/
├── src/icab/
│   ├── cim/          Canonical Information Model: entities, observations, relationships, JSON Schemas
│   ├── tep/           Tennessee Eastman Process simulator, fault injection, measurement registry
│   ├── context/       Context sources: historian, knowledge_graph, uns, opcua, mqtt, i3x
│   ├── gateway/       FastAPI app exposing context sources as agent tools
│   ├── agent/         Agent interface + implementations (baselines, LLM agent), gateway HTTP client
│   ├── trace/         Trace event models, collector, JSONL storage
│   ├── tasks/         BenchmarkTask model/registry/splits (M13-C) + context_combinations/isa95/context_conditions/experiment_design (v2)
│   ├── scenarios/      BenchmarkScenario model, YAML registry, ScenarioRunner (M5)
│   ├── usecases/       IndustrialUseCase model + registry -- ISA-95-level use cases (v2)
│   ├── evaluation/     Deterministic scoring (grounded evaluator, information-flow analysis)
│   ├── experiments/    ExperimentConfig/Record/Store, architecture combinations, H1-H5 hypotheses
│   ├── benchmark/      One-command orchestration: BenchmarkConfig/BenchmarkRunner (M13-D) + ContextExperimentRunner (v2)
│   ├── analysis/       Context necessity/sufficiency/composition/representation/efficiency/discoverability/matrix/reports (v2)
│   ├── architecture_health.py   Real architecture connectivity checks (v2, mandatory)
│   ├── reporting/       Aggregation, QA report, hypothesis reports, plotting -- reads results/ only
│   └── common/         Shared settings (pydantic-settings, .env-driven)
├── tests/
│   ├── unit/          Fast, deterministic, no external infrastructure
│   └── integration/    Real Postgres/Neo4j/MQTT/OPC UA/i3X; some gated behind a live-LLM flag
├── configs/
│   ├── benchmark/      Scenarios, tasks (tep-v1), tasks_v2 (tep-v2), splits, fault catalog
│   ├── usecases/       IndustrialUseCase YAML definitions, by ISA-95 level (v2)
│   ├── prototype/      Original prototype scenario/config (placeholders for budget/environment)
│   └── experiments/     Ablation/comparison experiment configs (placeholders)
├── docs/
│   ├── benchmark/       Task specification (v1 + v2), task inventory, splits, evaluation semantics
│   ├── architecture/    Per-component design docs (simulator, context architectures, LLM agent, ...)
│   └── research/        Research questions, hypotheses, experiment plan, development history
├── scripts/            Runnable entry points (run_benchmark.py, run_context_experiment.py, icab_v2_cli.py, check_architecture_health.py, ...)
├── services/           Per-component Dockerfiles (gateway, historian, knowledge_graph, opcua, i3x, tep)
├── data/               Reserved for future generated/ground_truth/raw datasets (placeholder)
└── results/            raw/traces/evaluations/aggregate/reports/figures/hypotheses/prototype (generated, gitignored)
```

## Tests

```powershell
uv run pytest -q
uv run pytest tests/unit -q
uv run pytest tests/integration -q
```

`tests/unit/` is fast, fully deterministic, and requires no external
services — it's what you run while making changes. `tests/integration/`
requires the Docker stack (`docker compose up -d`) — PostgreSQL/
TimescaleDB, Neo4j, MQTT, and the private OPC UA/i3X pair — and exercises
the real thing end to end rather than mocks. A handful of integration tests
additionally make live, metered calls to the configured LLM provider and are
gated behind `ICAB_RUN_LLM_INTEGRATION_TESTS=1`; they never run as part of
the default suite (`uv run pytest -q` skips them, reported as `skipped`).

Conceptually, the suite protects:

- **CIM/model validation** — entity/observation/relationship schemas stay internally consistent
- **TEP simulator** — deterministic, seeded simulation; the real `tep-studio` kernel behaves as expected
- **Fault injection** — each catalogued fault's empirically-verified behavior stays reproducible
- **Scenario runner** — deterministic seeds/warmup/fault-schedule/context-sync, correct `generation_id` provenance
- **Historian / Knowledge Graph / UNS / OPC UA / MQTT / i3X** — each context source's own contract, independent of any one agent
- **Architecture connectivity** — a REAL functional round trip (real data, not just "port is open") through every component at once (`tests/integration/test_architecture_connectivity.py`) -- a broken component must fail as itself, never as a misleading score
- **Gateway** — every tool route, argument validation, and error propagation
- **Agents** — baseline and LLM tool-calling behavior, termination handling, and that neither ever sees ground truth
- **Traces** — every tool call is recorded with correct context-acquired/consumed/latency/token accounting
- **Evaluation** — every deterministic score, including the acquired-vs-consumed context semantics (see `docs/architecture/llm-agent.md`)
- **Tasks** — schema validation, registry uniqueness, split integrity, ground-truth isolation
- **ISA-95 use cases / context combinations** — honest 0-use-case coverage at unsupported levels, the exact 127-combination space, tep-v2's task classification staying in sync with tep-v1's real inventory
- **Context analysis** — necessity/sufficiency/composition/representation/efficiency/failure-taxonomy/discoverability, always scoped to conditions actually tested
- **Context-condition resolution / experimental design** — exact/overshoot/unrealizable classification against the real architecture-dimension mapping, all five design strategies, and that a context-experiment campaign never counts a not-executed condition as a failure (`tests/integration/test_context_experiment_against_real_stack.py` exercises the real stack)
- **Benchmark orchestration** — run expansion, unique ids, no accidental overwrite, reproducibility, configuration metadata
- **Reporting** — the QA report and aggregate report render correctly, including failed-run and multi-run cases
- **Security** — ground truth and credentials never leak into a persisted artifact

We do not enumerate individual test names here — read the test modules
themselves (named for what they check) if you need that level of detail.

## Development

- Run `uv run pytest -q` before committing; add a regression test alongside
  any bug fix.
- Keep `tests/unit/` free of external-service dependencies — anything
  needing Postgres/Neo4j/MQTT/OPC UA/i3X belongs in `tests/integration/`.
- Never commit `.env`, a real API key, or generated `results/` content
  (see `.gitignore`).
- New scenarios/tasks/faults are a research-methodology decision, not a
  routine code change — see `docs/benchmark/specification.md` before
  adding one.

## Research Data Collection

Recommended workflow for an actual data-collection run:

1. **Smoke test** — confirm the pipeline works end to end (see
   [Quick Start](#quick-start)).
2. **Development** — iterate against `--split development` while tuning
   agent/architecture/budget configuration.
3. **Validation** — run `--split validation` to compare configurations
   before committing to a final run.
4. **Test** — run `--split test` exactly once per configuration you intend
   to report. **Test-split results should not be tuned against** — if you
   change configuration based on a test-split result and re-run, you are
   back in validation, not test, regardless of the flag you pass.

Give each real data-collection invocation an explicit `--name` so its
`results/reports/<name>-qa.md` and aggregate outputs are easy to find later;
rerunning the same `--name` is refused unless you pass `--force`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Agent Gateway is not reachable` | Start it: `uv run uvicorn icab.gateway.app:app --reload` (separate terminal, must stay running) |
| `required infrastructure is not reachable` | Run `docker compose up -d`; confirm with `docker ps` |
| A benchmark run raises about missing `ICAB_*` settings | Copy `.env.example` to `.env` and fill in real values (never commit `.env`) |
| i3X-related calls fail | The private i3X stack failed to build/start — check `docker compose logs i3x_server`; ICAB's other architectures work independently of it |
| Live-LLM integration tests are skipped | Expected by default — set `ICAB_RUN_LLM_INTEGRATION_TESTS=1` to opt in (makes real, metered calls) |
| `Address already in use` on port 8000/5432/7687/1883/8090 | Another process is already using that port — stop it, or pass `--gateway-url`/adjust `.env`/`docker-compose.yml` port mappings |
| Unexpected/stale files under `results/` | `results/` content is gitignored and meant to be disposable between data-collection runs — safe to delete anything under `results/{raw,traces,evaluations,aggregate,reports,figures}/` you don't need |
| `A benchmark with id '...' already has persisted results` | You reused an existing `--name` — pick a different one, omit `--name` for an auto-generated id, or pass `--force` to deliberately overwrite |

## License

Not yet finalized — see [`LICENSE`](LICENSE).
