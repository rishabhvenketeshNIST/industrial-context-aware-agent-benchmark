from icab.reporting.stats import summarize


def test_empty_values_produce_n_zero_and_none_stats():
    stats = summarize([])

    assert stats.n == 0
    assert stats.mean is None
    assert stats.median is None
    assert stats.stdev is None
    assert stats.minimum is None
    assert stats.maximum is None


def test_single_value_has_no_stdev_but_defined_mean_median_min_max():
    stats = summarize([5.0])

    assert stats.n == 1
    assert stats.mean == 5.0
    assert stats.median == 5.0
    assert stats.stdev is None  # not 0.0 -- a single point has no defined spread
    assert stats.minimum == 5.0
    assert stats.maximum == 5.0


def test_multiple_values_compute_all_statistics():
    stats = summarize([2.0, 4.0, 6.0])

    assert stats.n == 3
    assert stats.mean == 4.0
    assert stats.median == 4.0
    assert stats.stdev == 2.0
    assert stats.minimum == 2.0
    assert stats.maximum == 6.0
