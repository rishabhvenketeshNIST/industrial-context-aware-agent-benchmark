from unittest.mock import Mock

from icab.evaluation.cases import PROTOTYPE_REACTOR_CASE
from icab.experiments.architecture_comparison import (
    ArchitectureComparisonRunner,
)


def make_client(responses: list[dict]) -> Mock:
    client = Mock()

    responses_iter = iter(responses)

    def call_tool(
        tool_name: str,
        arguments: dict,
        *,
        step: int = 0,
        context_acquired: list[str] | None = None,
        context_consumed: list[str] | None = None,
    ) -> dict:
        result = next(responses_iter)

        client.trace_collector.record(
            step=step,
            action="tool_call",
            tool=tool_name,
            arguments=arguments,
            result=result,
            context_acquired=context_acquired,
            context_consumed=context_consumed,
        )

        return result

    client.call_tool.side_effect = call_tool
    client.trace_collector = None

    return client


def test_architecture_comparison_runner():
    uns_client = make_client(
        [
            {
                "nodes": [
                    {
                        "node_type": "measurement",
                        "canonical_id": (
                            "urn:icab:measurement:tep_pv_reactor_pressure"
                        ),
                        "display_name": "Pressure",
                    }
                ]
            },
            {
                "measurement_id": (
                    "urn:icab:measurement:tep_pv_reactor_pressure"
                ),
                "value": 2834.0,
            },
        ]
    )

    opcua_client = make_client(
        [
            {
                "nodes": [
                    {
                        "node_id": "ns=2;i=2",
                        "display_name": "Pressure",
                        "node_class": "Variable",
                    }
                ]
            },
            {
                "node_id": "ns=2;i=2",
                "value": 2834.0,
            },
        ]
    )

    runner = ArchitectureComparisonRunner(
        {
            "uns": uns_client,
            "opcua": opcua_client,
        }
    )

    results = runner.run(PROTOTYPE_REACTOR_CASE)

    assert len(results) == 2
    assert results[0].architecture == "uns"
    assert results[1].architecture == "opcua"

    assert results[0].tool_calls == 2
    assert results[1].tool_calls == 2

    assert results[0].case_id == "reactor_context_001"
    assert results[1].case_id == "reactor_context_001"

    assert results[0].normalized_context_score == 0.25
    assert results[1].normalized_context_score == 0.25