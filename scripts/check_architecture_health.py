"""
ICAB v2: produces the mandatory architecture connectivity/health report
(see `icab.architecture_health`) -- a machine-readable JSON and a
human-readable table, e.g.:

    Component       Status  Latency(ms)  Test
    Historian       PASS    142.3        get_current_value(...) after a real scenario preparation
    MQTT            PASS    58.1         discover/read a real, retained reactor-pressure message
    UNS             PASS    0.4          browse('site/tep') over the real TEP UNS tree
    OPCUA           PASS    61.7         browse the real, already-running TEP-backed OPC UA server
    i3X             PASS    390.2        get_objects/get_related_objects/get_value against the real private i3X instance
    KnowledgeGraph  PASS    12.9         get_entity_relationships(...) via the real discovery interface
    Gateway         PASS    334.9        a real HTTP POST to the gateway's own FastAPI route

No credentials are ever printed (see `icab.architecture_health
._redact_connection_string`).

Usage::

    uv run python scripts/check_architecture_health.py
    uv run python scripts/check_architecture_health.py --gateway-url http://localhost:8000
    uv run python scripts/check_architecture_health.py --json-out results/architecture_health.json
"""

from __future__ import annotations

import argparse
import sys

from icab.architecture_health import run_architecture_health_check
from icab.common.config import get_settings

DEFAULT_GATEWAY_URL = "http://localhost:8000"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY_URL,
        help=f"Agent Gateway base URL to include in the Gateway check. Default: {DEFAULT_GATEWAY_URL}.",
    )
    parser.add_argument("--skip-gateway", action="store_true", help="Skip the Gateway check (e.g. before the gateway process is started).")
    parser.add_argument("--json-out", default=None, help="Also write the machine-readable report to this path.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    settings = get_settings()
    gateway_url = None if args.skip_gateway else args.gateway_url

    report = run_architecture_health_check(gateway_url=gateway_url, settings=settings)

    name_width = max(len(result.component) for result in report.results)
    print(f"{'Component':<{name_width}}  {'Status':<6}  {'Latency(ms)':>11}  Test")
    for result in report.results:
        latency = f"{result.latency_ms:.1f}" if result.latency_ms is not None else "n/a"
        print(f"{result.component:<{name_width}}  {result.status:<6}  {latency:>11}  {result.test_performed}")
        if result.status != "PASS":
            print(f"{'':<{name_width}}  {'':<6}  {'':>11}  FAILURE: {result.failure_reason}")

    print()
    print(f"Overall: {'PASS' if report.all_passed else 'FAIL'} ({len(report.results)} component(s) checked)")
    if not report.all_passed:
        print(f"Failed: {', '.join(report.failed_components)}", file=sys.stderr)

    if args.json_out:
        from pathlib import Path

        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"Report written to: {path}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
