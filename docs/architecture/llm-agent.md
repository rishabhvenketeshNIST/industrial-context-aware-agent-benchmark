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

## Real-LLM integration testing

`tests/integration/test_llm_rchat.py` makes live calls to the configured
provider and is gated behind `ICAB_RUN_LLM_INTEGRATION_TESTS=1` (unlike the
other integration tests here, which assume the docker-compose stack is
simply up) -- it must never run silently as part of the default suite,
since it is billed/metered and provider availability is out of ICAB's
control.

## Known scope limits (as of M6/M7)

- `AGENT_TOOLS` covers the gateway's POST-based tools (historian, knowledge
  graph, UNS, OPC UA, MQTT). The GET-based i3X tools (`i3x_get_*`) are not
  yet included -- `AgentGatewayClient.call_tool` is POST-only today: adding
  i3X support means also giving it a request method, which was left out of
  this slice to avoid touching an existing, tested code path without a
  concrete need yet.
- There is no persistent multi-turn memory across separate `run()` calls;
  each investigation starts a fresh message history.
