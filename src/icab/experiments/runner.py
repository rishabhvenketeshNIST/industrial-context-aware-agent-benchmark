"""
Runs one M9 experiment: prepares a BenchmarkScenario against the real
simulator/context architectures (icab.scenarios.ScenarioRunner, M5),
builds the configured agent, runs it against the real Agent Gateway, and
evaluates the result with the M8 GroundedInvestigationEvaluator -- without
persisting anything itself (see icab.experiments.storage for that).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from icab.agent.architecture_aware import ArchitectureAwareAgent
from icab.agent.baseline.scenario_aware import ScenarioAwareBaselineAgent
from icab.agent.baseline.structured_retrieval import StructuredRetrievalAgent
from icab.agent.client import AgentGatewayClient
from icab.agent.context_aware import ContextAwareAgent
from icab.agent.interface import Agent
from icab.agent.llm.agent import DEFAULT_MAX_STEPS, LLMInvestigationAgent
from icab.agent.llm.client import LLMClient, OpenAICompatibleLLMClient
from icab.agent.llm.tools import tools_for_architectures
from icab.common.config import get_settings
from icab.evaluation.grounded import GroundedInvestigationEvaluator
from icab.evaluation.information_flow import InformationFlowAnalyzer
from icab.scenarios import BenchmarkScenarioRegistry
from icab.scenarios.models import BenchmarkScenario
from icab.scenarios.runner import ScenarioRunner
from icab.tasks.benchmark_task import BenchmarkTask
from icab.trace.collector import TraceCollector
from icab.trace.models import TraceEvent

from .architecture_combinations import get_combination
from .models import (
    LEGACY_DETERMINISTIC_AGENT_KINDS,
    AgentType,
    DeterministicAgentKind,
    ExperimentConfig,
    ExperimentRecord,
    ExperimentRunStatus,
    RunValidity,
    compute_configuration_hash,
)

LLMClientFactory = Callable[[ExperimentConfig], LLMClient]


def _icab_version() -> str | None:
    try:
        return _pkg_version("icab")
    except PackageNotFoundError:
        return None


class ExperimentRunner:
    """Executes one ExperimentConfig against a BenchmarkScenario and the real gateway."""

    def __init__(
        self,
        *,
        gateway_base_url: str,
        scenario_runner: ScenarioRunner,
        scenario_registry: BenchmarkScenarioRegistry,
        evaluator: GroundedInvestigationEvaluator | None = None,
        llm_client_factory: LLMClientFactory | None = None,
    ) -> None:
        self.gateway_base_url = gateway_base_url
        self.scenario_runner = scenario_runner
        self.scenario_registry = scenario_registry
        self.evaluator = evaluator or GroundedInvestigationEvaluator()
        self._llm_client_factory = llm_client_factory or self._default_llm_client_factory
        self._information_flow_analyzer = InformationFlowAnalyzer()

    def run(
        self,
        config: ExperimentConfig,
        *,
        run_id: str | None = None,
        experiment_id: str | None = None,
    ) -> tuple[ExperimentRecord, list[TraceEvent]]:
        """
        Run one experiment: prepares the scenario (resets and re-runs the
        TEP simulator with its own seed/warmup/fault schedule, syncing it
        into the historian/knowledge graph/MQTT), then runs the configured
        agent against it. Returns ``(record, trace)`` -- persistence is the
        caller's job (see `icab.experiments.storage.ExperimentResultStore`).

        See `compare_architectures` for running several architecture
        configs against one shared scenario preparation (what "holds the
        process condition constant" across an architecture comparison
        actually means here -- and its OPC UA/i3X caveat).
        """

        scenario = self.scenario_registry.get(config.scenario_id)
        run_result = self.scenario_runner.prepare(scenario)

        resolved_run_id = run_id or self._default_run_id(config)

        return self._run_prepared(
            scenario,
            config,
            run_id=resolved_run_id,
            experiment_id=experiment_id or resolved_run_id,
            generation_id=run_result.generation_id,
        )

    def run_task(
        self,
        task: BenchmarkTask,
        config: ExperimentConfig,
        *,
        scenario: BenchmarkScenario | None = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
        benchmark_version: str | None = None,
        git_commit: str | None = None,
    ) -> tuple[ExperimentRecord, list[TraceEvent]]:
        """
        M13-D: the benchmark-orchestrator entry point -- like `run()`, but
        against a `BenchmarkTask` (icab.tasks, M13-C) rather than a bare
        scenario: the agent's objective is the TASK's objective (not the
        underlying scenario's, which may be broader), and evaluation goes
        through `GroundedInvestigationEvaluator.evaluate_task` (the task's
        own, possibly narrower, ground truth) rather than `.evaluate`.

        ``config.scenario_id`` is ignored in favor of ``task.scenario_id``
        -- the caller is expected to have built `config` from the task
        (see `icab.benchmark.runner.BenchmarkRunner`), but this keeps the
        scenario that's actually prepared unambiguous either way.

        ``scenario``, when given, is prepared and run AS GIVEN instead of
        looking it up fresh from `self.scenario_registry` -- this is how
        `icab.benchmark.runner.BenchmarkRunner` applies a `--seeds`
        override (`scenario.model_copy(update={"seed": seed})`) without
        introducing a second scenario-loading path: the caller still gets
        the scenario from the SAME registry first, then only overrides
        the one field `--seeds` is documented to vary.
        """

        resolved_scenario = scenario if scenario is not None else self.scenario_registry.get(task.scenario_id)
        run_result = self.scenario_runner.prepare(resolved_scenario)

        resolved_run_id = run_id or self._default_run_id(config)

        return self._run_prepared(
            resolved_scenario,
            config,
            run_id=resolved_run_id,
            experiment_id=experiment_id or resolved_run_id,
            generation_id=run_result.generation_id,
            task=task,
            benchmark_version=benchmark_version,
            git_commit=git_commit,
        )

    def compare_architectures(
        self,
        scenario_id: str,
        architecture_configs: list[list[str]],
        *,
        agent_type: AgentType = AgentType.LLM,
        deterministic_agent: DeterministicAgentKind | None = None,
        llm_model: str | None = None,
        llm_temperature: float | None = None,
        max_steps: int | None = None,
        experiment_id: str | None = None,
    ) -> list[tuple[ExperimentRecord, list[TraceEvent]]]:
        """
        Run the SAME scenario once per entry in ``architecture_configs``,
        holding everything else fixed (seed, fault schedule, objective,
        model/config) and varying only which tools the agent is given --
        the controlled-comparison pattern this milestone's research design
        requires. See the module docstring / docs/benchmark/experiments.md
        for what "held constant" does and doesn't cover.
        """

        experiment_id = experiment_id or f"compare-{scenario_id}-{uuid.uuid4().hex[:8]}"

        # Prepare the scenario ONCE: every architecture variant below
        # investigates the exact same already-synced historian/knowledge
        # graph/MQTT state (same generation_id), not a fresh (still
        # deterministic, but redundant) re-run per architecture.
        scenario = self.scenario_registry.get(scenario_id)
        run_result = self.scenario_runner.prepare(scenario)

        runs = []

        for architectures in architecture_configs:
            config = ExperimentConfig(
                scenario_id=scenario_id,
                architectures=architectures,
                agent_type=agent_type,
                deterministic_agent=deterministic_agent,
                llm_model=llm_model,
                llm_temperature=llm_temperature,
                max_steps=max_steps,
            )
            run_id = f"{experiment_id}-{'+'.join(architectures)}"

            # Re-implements run()'s body rather than calling run() (which
            # would re-prepare the scenario) -- see run()'s docstring note.
            record, trace = self._run_prepared(
                scenario,
                config,
                run_id=run_id,
                experiment_id=experiment_id,
                generation_id=run_result.generation_id,
            )
            runs.append((record, trace))

        return runs

    def compare_combinations(
        self,
        scenario_id: str,
        combination_keys: list[str],
        *,
        agent_type: AgentType = AgentType.LLM,
        deterministic_agent: DeterministicAgentKind | None = None,
        llm_model: str | None = None,
        llm_temperature: float | None = None,
        max_steps: int | None = None,
        experiment_id: str | None = None,
    ) -> list[tuple[ExperimentRecord, list[TraceEvent]]]:
        """
        Like `compare_architectures`, but takes named
        `icab.experiments.architecture_combinations` keys instead of raw
        architecture lists -- the M10 first-class-combinations entry point.
        Each resulting `ExperimentConfig.architecture_combination_key` is
        set so aggregates can group by combination, in addition to the raw
        `architectures` list that's what's actually enforced on the agent.
        """

        experiment_id = experiment_id or f"compare-{scenario_id}-{uuid.uuid4().hex[:8]}"

        scenario = self.scenario_registry.get(scenario_id)
        run_result = self.scenario_runner.prepare(scenario)

        runs = []

        for key in combination_keys:
            combination = get_combination(key)
            config = ExperimentConfig(
                scenario_id=scenario_id,
                architectures=list(combination.architectures),
                architecture_combination_key=combination.key,
                agent_type=agent_type,
                deterministic_agent=deterministic_agent,
                llm_model=llm_model,
                llm_temperature=llm_temperature,
                max_steps=max_steps,
            )
            run_id = f"{experiment_id}-{combination.key}"

            record, trace = self._run_prepared(
                scenario,
                config,
                run_id=run_id,
                experiment_id=experiment_id,
                generation_id=run_result.generation_id,
            )
            runs.append((record, trace))

        return runs

    def _run_prepared(
        self,
        scenario: BenchmarkScenario,
        config: ExperimentConfig,
        *,
        run_id: str,
        experiment_id: str,
        generation_id: str,
        task: BenchmarkTask | None = None,
        benchmark_version: str | None = None,
        git_commit: str | None = None,
    ) -> tuple[ExperimentRecord, list[TraceEvent]]:
        """
        ``task=None`` (the default) is the original M9-M12 scenario-only
        path, byte-for-byte unchanged: objective/evaluation/ground truth
        all come from ``scenario``, and the M13-D-only record fields
        (fault_id/scenario_version/task_version/benchmark_version/
        git_commit/configuration_hash) are populated the same way they
        always would be for a plain scenario run -- fault_id/
        scenario_version are properties of the scenario itself either
        way, task_version is simply None, and benchmark_version/
        git_commit are None unless the caller (the M13-D orchestrator)
        passes them in.
        """

        resolved_config = self._resolve_config(config)
        validity, validity_reason = self._validity_for(resolved_config)

        objective = task.objective if task is not None else scenario.objective

        started_at = datetime.now(UTC)
        trace_collector = TraceCollector()
        gateway_client = AgentGatewayClient(self.gateway_base_url, trace_collector=trace_collector)

        result = None
        status = ExperimentRunStatus.COMPLETED
        error: str | None = None

        try:
            agent = self._build_agent(resolved_config, gateway_client)
            result = agent.run(
                objective=objective,
                initial_state={
                    "scenario_id": scenario.scenario_id,
                    "difficulty": scenario.difficulty.value,
                },
            )
        except Exception as error_instance:  # noqa: BLE001
            status = ExperimentRunStatus.FAILED
            error = f"{type(error_instance).__name__}: {error_instance}"

        completed_at = datetime.now(UTC)
        trace = trace_collector.events()

        evaluation = None
        if result is not None:
            if task is not None:
                evaluation = self.evaluator.evaluate_task(
                    task, result, trace, generation_id=generation_id
                )
            else:
                evaluation = self.evaluator.evaluate(
                    scenario, result, trace, generation_id=generation_id
                )

        information_flow = self._information_flow_analyzer.analyze(trace)
        total_latency_ms = self._sum_latency_ms(trace)
        total_tokens = self._sum_total_tokens(trace)

        fault_id = scenario.faults[0].disturbance if scenario.faults else None

        record = ExperimentRecord(
            run_id=run_id,
            experiment_id=experiment_id,
            config=resolved_config,
            scenario_difficulty=scenario.difficulty.value,
            simulation_seed=scenario.seed,
            generation_id=generation_id,
            icab_version=_icab_version(),
            benchmark_version=benchmark_version,
            git_commit=git_commit,
            fault_id=fault_id,
            scenario_version=scenario.version,
            task_version=task.version if task is not None else None,
            configuration_hash=compute_configuration_hash(resolved_config),
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            error=error,
            validity=validity,
            validity_reason=validity_reason,
            result=result,
            evaluation=evaluation,
            information_flow=information_flow,
            trace_event_count=len(trace),
            total_latency_ms=total_latency_ms,
            total_tokens=total_tokens,
        )

        return record, trace

    @staticmethod
    def _sum_latency_ms(trace: list[TraceEvent]) -> float | None:
        latencies = [event.latency_ms for event in trace if event.latency_ms is not None]
        return sum(latencies) if latencies else None

    @staticmethod
    def _sum_total_tokens(trace: list[TraceEvent]) -> int | None:
        totals = [
            event.token_usage["total_tokens"]
            for event in trace
            if event.token_usage is not None and "total_tokens" in event.token_usage
        ]
        return sum(totals) if totals else None

    # -- agent construction ---------------------------------------------------

    def _build_agent(self, config: ExperimentConfig, gateway_client: AgentGatewayClient) -> Agent:
        if config.agent_type == AgentType.DETERMINISTIC:
            return self._build_deterministic_agent(config, gateway_client)
        return self._build_llm_agent(config, gateway_client)

    @staticmethod
    def _build_deterministic_agent(
        config: ExperimentConfig,
        gateway_client: AgentGatewayClient,
    ) -> Agent:
        kind = config.deterministic_agent

        if kind is None:
            raise ValueError(
                "deterministic_agent is required when agent_type == 'deterministic'"
            )

        if kind == DeterministicAgentKind.STRUCTURED_RETRIEVAL:
            return StructuredRetrievalAgent(gateway_client)

        if kind == DeterministicAgentKind.CONTEXT_AWARE:
            return ContextAwareAgent(gateway_client)

        if kind == DeterministicAgentKind.ARCHITECTURE_AWARE:
            if len(config.architectures) != 1:
                raise ValueError(
                    "ArchitectureAwareAgent requires exactly one architecture, "
                    f"got: {config.architectures}"
                )
            return ArchitectureAwareAgent(gateway_client, architecture=config.architectures[0])

        if kind == DeterministicAgentKind.SCENARIO_AWARE:
            kwargs = {}
            if config.deterministic_equipment_key:
                kwargs["equipment_key"] = config.deterministic_equipment_key
            return ScenarioAwareBaselineAgent(gateway_client, **kwargs)

        raise ValueError(f"Unknown deterministic agent kind: {kind}")

    def _build_llm_agent(
        self,
        config: ExperimentConfig,
        gateway_client: AgentGatewayClient,
    ) -> Agent:
        llm = self._llm_client_factory(config)
        tools = tools_for_architectures(config.architectures)

        return LLMInvestigationAgent(
            gateway_client,
            llm,
            tools=tools,
            max_steps=config.max_steps or DEFAULT_MAX_STEPS,
            max_tool_calls=config.max_tool_calls,
            max_context_tokens=config.max_context_tokens,
            max_wall_time_seconds=config.max_wall_time_seconds,
        )

    @staticmethod
    def _default_llm_client_factory(config: ExperimentConfig) -> LLMClient:
        settings = get_settings()
        model = config.llm_model or settings.llm_model

        if not (settings.llm_base_url and settings.llm_api_key and model):
            raise RuntimeError(
                "LLM provider is not configured -- set ICAB_LLM_BASE_URL, "
                "ICAB_LLM_API_KEY, and ICAB_LLM_MODEL (or pass "
                "ExperimentConfig.llm_model)."
            )

        return OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=model,
            temperature=config.llm_temperature if config.llm_temperature is not None else 0.0,
        )

    def _resolve_config(self, config: ExperimentConfig) -> ExperimentConfig:
        """Fill in any provider/budget defaults so the persisted record captures what actually ran."""

        if config.agent_type != AgentType.LLM:
            return config.model_copy(
                update={
                    "llm_model": None,
                    "llm_temperature": None,
                    "max_steps": None,
                    "max_tool_calls": None,
                    "max_context_tokens": None,
                    "max_wall_time_seconds": None,
                }
            )

        settings = get_settings()
        return config.model_copy(
            update={
                "llm_model": config.llm_model or settings.llm_model,
                "llm_temperature": (
                    config.llm_temperature if config.llm_temperature is not None else 0.0
                ),
                "max_steps": config.max_steps or DEFAULT_MAX_STEPS,
            }
        )

    @staticmethod
    def _default_run_id(config: ExperimentConfig) -> str:
        architectures = "+".join(config.architectures)
        return f"{config.scenario_id}-{architectures}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _validity_for(config: ExperimentConfig) -> tuple[RunValidity, str | None]:
        """
        Whether this config is eligible for the main architecture-comparison
        benchmark. Legacy deterministic baselines never are, regardless of
        whether they complete successfully -- see
        docs/research/experiment-plan.md for the incident that motivated
        this and ExperimentResultStore.write_aggregate for where it's
        enforced.
        """

        if (
            config.agent_type == AgentType.DETERMINISTIC
            and config.deterministic_agent in LEGACY_DETERMINISTIC_AGENT_KINDS
        ):
            return (
                RunValidity.LEGACY_CONTROL_ONLY,
                (
                    f"{config.deterministic_agent.value} is a legacy, pre-M5 "
                    "deterministic baseline hard-coded to static-prototype "
                    "canonical ids/paths -- it does not access this scenario's "
                    "real data. Regression/control use only; excluded from "
                    "the main architecture-comparison benchmark by default."
                ),
            )

        return RunValidity.VALID, None
