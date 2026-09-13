"""
M13-B: empirically characterize every one of the real TEP simulator's 28
disturbances and (re)write `configs/benchmark/fault_catalog.json`.

Runs entirely against the real, in-process TEP simulator -- no gateway,
no historian/KG/MQTT, no LLM calls. Two baselines (one per seed) plus one
faulted run per (disturbance, seed) pair are simulated in memory; nothing
is persisted except the final aggregated catalog.

Usage::

    uv run python scripts/characterize_tep_disturbances.py
    uv run python scripts/characterize_tep_disturbances.py --seeds 101 202 303
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from importlib.metadata import version as _pkg_version

from tep_studio import list_disturbances

from icab.tep.fault_characterization import (
    DEFAULT_DEVIATION_THRESHOLD_STDEVS,
    DEFAULT_DURATION_HOURS,
    DEFAULT_SAMPLE_INTERVAL_HOURS,
    DEFAULT_WARMUP_HOURS,
    characterize_all_disturbances,
)
from icab.tep.faults import DEFAULT_CATALOG_PATH, FaultCatalog, build_fault_catalog_entry, write_fault_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=[101, 202], help="Seeds to characterize each disturbance at."
    )
    parser.add_argument("--warmup-hours", type=float, default=DEFAULT_WARMUP_HOURS)
    parser.add_argument("--duration-hours", type=float, default=DEFAULT_DURATION_HOURS)
    parser.add_argument("--sample-interval-hours", type=float, default=DEFAULT_SAMPLE_INTERVAL_HOURS)
    parser.add_argument("--deviation-threshold-stdevs", type=float, default=DEFAULT_DEVIATION_THRESHOLD_STDEVS)
    parser.add_argument("--output", default=str(DEFAULT_CATALOG_PATH))

    args = parser.parse_args()
    seeds = tuple(args.seeds)

    print(f"Characterizing 28 disturbances at seeds {seeds} "
          f"(warmup={args.warmup_hours}h, duration={args.duration_hours}h)...")

    results = characterize_all_disturbances(
        seeds=seeds,
        warmup_hours=args.warmup_hours,
        duration_hours=args.duration_hours,
        sample_interval_hours=args.sample_interval_hours,
        deviation_threshold_stdevs=args.deviation_threshold_stdevs,
    )

    names_by_id = dict(list_disturbances())
    try:
        tep_studio_version = _pkg_version("tep-studio")
    except Exception:  # noqa: BLE001
        tep_studio_version = "unknown"

    characterized_at = datetime.now(UTC).isoformat()

    entries = []
    for disturbance_id, characterizations in results.items():
        entry = build_fault_catalog_entry(
            disturbance_id,
            names_by_id[disturbance_id],
            characterizations,
            tep_studio_version=tep_studio_version,
            characterized_at=characterized_at,
        )
        entries.append(entry)

        status = "VERIFIED" if entry.empirically_verified else ("injectable" if entry.icab_injectable else "FAILED")
        print(
            f"  {disturbance_id:8s} [{status:9s}] "
            f"tripped={entry.plant_tripped_in_any_seed!s:5s} "
            f"affected={len(entry.affected_measurements)} measurements"
        )

    catalog = FaultCatalog(entries=entries)
    path = write_fault_catalog(catalog, args.output)

    verified_count = len(catalog.verified())
    injectable_count = sum(1 for entry in entries if entry.icab_injectable)
    print()
    print(f"{len(entries)} disturbances supported by the simulator")
    print(f"{injectable_count} injectable through ICAB (every tested seed ran without error)")
    print(f"{verified_count} empirically verified (repeatable measurable effect or trip)")
    print(f"Catalog written to: {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
