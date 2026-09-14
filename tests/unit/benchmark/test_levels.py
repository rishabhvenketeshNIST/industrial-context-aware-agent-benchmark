"""Unit tests for icab.benchmark.levels -- the six ISA-95-level benchmark definitions."""

from __future__ import annotations

import pytest

from icab.benchmark.levels import LEVEL_BENCHMARKS, executable_levels, get_level_benchmark
from icab.tasks.isa95 import ISA95Level


class TestSixBenchmarkDefinitions:
    def test_exactly_six_levels_are_defined(self):
        assert set(LEVEL_BENCHMARKS) == set(ISA95Level)
        assert len(LEVEL_BENCHMARKS) == 6

    def test_every_level_declares_framework_support(self):
        for definition in LEVEL_BENCHMARKS.values():
            assert definition.framework_supported is True

    def test_every_level_is_executable_with_fifty_question_content(self):
        # ICAB v3 50-question milestone: every level now has a real
        # (Equipment/Process Cell) or controlled/mixed
        # (Enterprise/Site/Area/Work Center) question bank -- see
        # docs/benchmark/specification-v3.md. None are unsupported
        # anymore, but the PROVENANCE of each level's data is explicit.
        for definition in LEVEL_BENCHMARKS.values():
            assert definition.data_supported is True
            assert definition.executable is True
            assert definition.coverage_note  # non-empty, explains provenance

    def test_data_provenance_is_declared_honestly_per_level(self):
        expected = {
            ISA95Level.ENTERPRISE: "controlled_synthetic",
            ISA95Level.SITE: "mixed",
            ISA95Level.AREA: "mixed",
            ISA95Level.WORK_CENTER: "controlled_synthetic",
            ISA95Level.PROCESS_CELL: "real_tep",
            ISA95Level.EQUIPMENT: "real_tep",
        }
        for level, provenance in expected.items():
            assert get_level_benchmark(level).data_provenance == provenance

    def test_no_level_claims_real_tep_provenance_without_actually_using_tep(self):
        # A structural honesty check: only the two levels TEP genuinely
        # models richly may claim "real_tep" alone.
        real_only = {level for level, d in LEVEL_BENCHMARKS.items() if d.data_provenance == "real_tep"}
        assert real_only == {ISA95Level.PROCESS_CELL, ISA95Level.EQUIPMENT}

    def test_each_level_has_its_own_distinct_results_root(self):
        roots = [str(definition.results_root) for definition in LEVEL_BENCHMARKS.values()]
        assert len(roots) == len(set(roots))
        for definition in LEVEL_BENCHMARKS.values():
            assert str(definition.results_root) == f"results\\{definition.isa95_level.value}" or str(definition.results_root) == f"results/{definition.isa95_level.value}"

    def test_each_level_has_its_own_distinct_question_bank_dir(self):
        dirs = [str(definition.question_bank_dir) for definition in LEVEL_BENCHMARKS.values()]
        assert len(dirs) == len(set(dirs))

    def test_get_level_benchmark_unknown_level_raises(self):
        with pytest.raises(KeyError):
            get_level_benchmark("not-a-real-level")  # type: ignore[arg-type]


class TestExecutableLevels:
    def test_returns_all_six_levels(self):
        assert set(executable_levels()) == set(ISA95Level)
