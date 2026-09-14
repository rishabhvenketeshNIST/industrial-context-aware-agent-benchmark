# LLM Investigation Agent

## What this is

`icab.agent.llm` (added in the M6/M7 milestone) is a second, LLM-backed
implementation of the `Agent` interface, alongside (not instead of) the
deterministic baselines `StructuredRetrievalAgent`, `ContextAwareAgent`, and
`ArchitectureAwareAgent`. Those remain the controlled baseline the LLM agent
is compared against.

Loop:

```
objective -> LLM -> choose ICAB tool -> tool result/observation -> LLM
-> choose next tool -> ... -> submit_investigation -> InvestigationResult
```

The agent reaches process/context information *only* through
`AgentGatewayClient.call_tool` (the Agent Gateway's HTTP tool API) --
never through a direct database/broker/OPC UA connection. Available tools
come from `icab.agent.llm.tools.AGENT_TOOLS`, whose parameter schemas are
generated from the gateway's own Pydantic request models
(`icab.gateway.schemas`), so the LLM-visible tool contract cannot silently
drift from the real gateway API.

## Provider configuration

`icab.agent.llm.client.LLMClient` is a small abstraction
(`generate(messages, tools) -> LLMResponse`) so the agent never depends on a
specific provider SDK. Two implementations:

- `OpenAICompatibleLLMClient` -- the real client, backed by the `openai`
  Python SDK pointed at a configurable `base_url`. This project is
  configured (via `.env`, never committed) to use **NIST RChat**
  (`https://rchat.nist.gov/api/v1`, an OpenAI-compatible, vLLM-backed
  endpoint), model `gemma-4-31B-it`, which was verified to support native
  `tools`/`tool_choice="auto"` function calling before this was built.
  Nothing about the client is NIST-RChat-specific; any OpenAI-compatible
  endpoint works by changing `ICAB_LLM_BASE_URL`/`ICAB_LLM_MODEL`.
- `MockLLMClient` -- a deterministic, scriptable fake (a fixed list of
  `LLMResponse`s played back in order) used by every unit test, so the
  agent's tool-loop logic is fully covered without network access, an API
  key, or nondeterminism.

`ICABSettings` gained `llm_provider`/`llm_base_url`/`llm_api_key`/
`llm_model`, all optional (default `None`) so existing `.env` files without
them keep working unchanged.

## What is (and is not) recorded

The agent's own hidden reasoning is never captured or exposed as benchmark
output -- only structured tool decisions (name + arguments) and their
observations (raw tool results) flow through `InvestigationResult.findings`
and `.evidence`, plus the same `TraceCollector`/`context_acquired` mechanism
`ArchitectureAwareAgent` already uses (`AgentGatewayClient.call_tool(...,
context_acquired=[identifier])`).

## `context_acquired` vs. `context_consumed`

Audited 2026-09 (a researcher flagged a D1 run showing `context_acquired=1,
context_consumed=0` after a single `get_current_value` call whose returned
value the agent's own conclusion clearly used, and asked whether that was a
bug). Findings:

- `context_acquired`: attached at EVERY tool call, by every agent including
  this one (`_execute_tool`, `context_acquired=[identifier] if identifier
  else None`) -- "this specific call's own target identifier."
- `context_consumed`: a NARROWER, separate concept, established by the
  deterministic baselines (`ArchitectureAwareAgent`, `ScenarioAwareBaselineAgent`)
  before this agent existed -- "an identifier ACQUIRED by an EARLIER
  discovery-type call (`browse_uns`/`get_entity_relationships`/`opcua_browse`/
  `i3x_get_objects`/`i3x_get_related_objects`) in the SAME trace, exploited to
  target a LATER, more specific value-retrieval call." Concretely: those
  agents' `browse_uns(...)` call tags `context_acquired=[path]`, then every
  subsequent `get_current_value(...)` call for a measurement that browse
  turned up tags `context_consumed=[path]` -- "the earlier discovery is what
  made this later, specific call possible."
- **`LLMInvestigationAgent` does not currently populate `context_consumed`
  for any call.** `_execute_tool` only ever passes `context_acquired`. This
  is a genuine, previously undocumented gap (an earlier revision of
  `docs/benchmark/evaluation.md` incorrectly claimed this agent "already
  populates" both fields) -- but NOT a scoring bug: `context_acquired`/
  `context_consumed` feed no score in `GroundedInvestigationEvaluator`
  (`required_evidence_score`, `grounding_score`, etc. are computed
  independently, directly from the conclusion text and trace observations).
  Extending this agent to attribute a specific later call back to a specific
  earlier discovery would require inferring which of possibly several prior
  discoveries "caused" a given LLM tool choice -- unlike the fixed
  baselines, which mechanically iterate over their own single browse
  response, the LLM's tool sequence has no such single, deterministic
  correlation to attribute. Rather than invent a heuristic for that
  attribution, this is left unpopulated and documented here plainly.
- **A run with `context_acquired=1, context_consumed=0` after one direct
  tool call (no discovery step at all -- e.g. a historian-only D1 task that
  goes straight to `get_current_value`) is CORRECT under this definition,
  not evidence the agent failed to use its own data.** Whether acquired
  evidence was actually used in the conclusion is a different question,
  already answered by `required_evidence_score`/`grounding_score`/
  `InvestigationResult.evidence` -- see
  `results/reports/<benchmark_id>-qa.md`'s per-run "Metrics" section, which
  labels `context_consumed` explicitly as a hand-off count for exactly this
  reason.

## Real-LLM integration testing

`tests/integration/test_llm_rchat.py` makes live calls to the configured
provider and is gated behind `ICAB_RUN_LLM_INTEGRATION_TESTS=1` (unlike the
other integration tests here, which assume the docker-compose stack is
simply up) -- it must never run silently as part of the default suite,
since it is billed/metered and provider availability is out of ICAB's
control.

## Known scope limits

- There is no persistent multi-turn memory across separate `run()` calls;
  each investigation starts a fresh message history.

**Update (private i3X milestone):** `AGENT_TOOLS` originally covered only
the gateway's POST-based tools; `AgentGatewayClient.call_tool` gained a
`method` parameter (`GET` support, using query params instead of a JSON
body) and `AGENT_TOOLS` now also includes `i3x_get_objects`/`i3x_get_object`/
`i3x_get_related_objects`/`i3x_get_value`/`i3x_get_history` --
`AgentTool` accordingly accepts either a Pydantic `request_model` (existing
tools) or a hand-written `parameters` JSON Schema plus `http_method="GET"`
(the i3X tools, whose gateway routes take individual query parameters
rather than a request body). See
`docs/architecture/i3x-private-server.md`.
