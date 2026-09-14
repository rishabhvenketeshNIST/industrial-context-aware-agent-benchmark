"""
One `manifest.json` per ISA-95-level benchmark results tree
(`results/<level>/manifest.json`) -- the single, authoritative
description of what that level's currently-active results actually
contain, per the ICAB context-requirement direction's explicit manifest
field list.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from icab.benchmark.config import get_git_commit
from icab.benchmark.levels import ISA95BenchmarkDefinition
from icab.experiments.models import ExperimentRecord


class BenchmarkManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    isa95_level: str
    benchmark_version: str
    question_bank_version: str
    #: icab.benchmark.levels.BENCHMARK_LEVELS_VERSION -- the level-
    #: benchmark STRUCTURE's own version, distinct from this one
    #: benchmark's question_bank_version.
    experiment_protocol_version: str

    git_commit: str | None
    #: sha256 over this manifest's own descriptive fields (NOT a per-run
    #: configuration_hash -- see icab.experiments.models
    #: .compute_configuration_hash for that) -- lets two manifests be
    #: compared for "same declared configuration" without diffing every
    #: field by hand.
    config_hash: str

    created_at: datetime

    n_questions: int
    n_use_cases: int
    n_instances: int
    n_repetitions: int

    architectures: list[str]
    scenarios: list[str]
    context_conditions: list[str]

    #: Every run_id this manifest's counts were computed from --
    #: traceability from the manifest itself back to the raw records.
    run_ids: list[str]


def build_manifest(
    definition: ISA95BenchmarkDefinition,
    records: list[ExperimentRecord],
) -> BenchmarkManifest:
    """Computed ONLY from already-persisted records for this level -- never a static/hand-maintained count."""

    instances = {r.config.question_instance_id for r in records if r.config.question_instance_id}
    questions = {r.config.question_id for r in records if r.config.question_id}
    use_cases = {r.config.use_case_id for r in records if r.config.use_case_id}
    architectures = {architecture for r in records for architecture in r.config.architectures}
    scenarios = {r.config.scenario_id for r in records}
    context_conditions = {r.config.context_combination_id for r in records if r.config.context_combination_id}

    descriptive = {
        "benchmark_id": definition.benchmark_id,
        "isa95_level": definition.isa95_level.value,
        "question_bank_version": definition.question_bank_version,
    }
    config_hash = _hash_descriptive(descriptive)

    return BenchmarkManifest(
        benchmark_id=definition.benchmark_id,
        isa95_level=definition.isa95_level.value,
        benchmark_version=definition.question_bank_version,
        question_bank_version=definition.question_bank_version,
        experiment_protocol_version=_levels_version(),
        git_commit=get_git_commit(),
        config_hash=config_hash,
        created_at=datetime.now(UTC),
        n_questions=len(questions),
        n_use_cases=len(use_cases),
        n_instances=len(instances),
        n_repetitions=len(records),
        architectures=sorted(architectures),
        scenarios=sorted(scenarios),
        context_conditions=sorted(context_conditions),
        run_ids=sorted(r.run_id for r in records),
    )


def write_manifest(definition: ISA95BenchmarkDefinition, records: list[ExperimentRecord], *, root: Path | None = None) -> Path:
    manifest = build_manifest(definition, records)
    target_root = root or definition.results_root
    target_root.mkdir(parents=True, exist_ok=True)
    path = target_root / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def _hash_descriptive(descriptive: dict) -> str:
    import hashlib

    canonical = json.dumps(descriptive, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _levels_version() -> str:
    from icab.benchmark.levels import BENCHMARK_LEVELS_VERSION

    return BENCHMARK_LEVELS_VERSION
