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

    def test_enterprise_site_work_center_are_honestly_unsupported(self):
        for level in (ISA95Level.ENTERPRISE, ISA95Level.SITE, ISA95Level.WORK_CENTER):
            definition = get_level_benchmark(level)
            assert definition.data_supported is False
            assert definition.executable is False
            assert definition.coverage_note  # non-empty, explains why

    def test_area_process_cell_equipment_are_executable(self):
        for level in (ISA95Level.AREA, ISA95Level.PROCESS_CELL, ISA95Level.EQUIPMENT):
            definition = get_level_benchmark(level)
            assert definition.data_supported is True
            assert definition.executable is True

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
    def test_returns_exactly_area_process_cell_equipment(self):
        assert set(executable_levels()) == {ISA95Level.AREA, ISA95Level.PROCESS_CELL, ISA95Level.EQUIPMENT}
