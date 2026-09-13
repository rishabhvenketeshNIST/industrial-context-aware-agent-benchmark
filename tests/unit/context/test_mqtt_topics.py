import pytest

from icab.context.mqtt.topics import (
    build_topic,
    equipment_key_from_canonical_id,
    parse_topic,
)


def test_build_topic_joins_segments_under_icab_root():
    assert build_topic("tep", "reactor", "reactor_pressure") == (
        "icab/tep/reactor/reactor_pressure"
    )


def test_build_topic_requires_at_least_one_segment():
    with pytest.raises(ValueError):
        build_topic()


def test_build_topic_rejects_empty_segments():
    with pytest.raises(ValueError):
        build_topic("tep", "")


def test_equipment_key_from_canonical_id():
    assert equipment_key_from_canonical_id("urn:icab:equipment:reactor") == "reactor"
    assert (
        equipment_key_from_canonical_id("urn:icab:equipment:feed-system")
        == "feed-system"
    )


def test_parse_topic_returns_segments_after_root():
    assert parse_topic("icab/tep/reactor/reactor_pressure") == [
        "tep",
        "reactor",
        "reactor_pressure",
    ]


def test_parse_topic_returns_none_for_foreign_namespace():
    assert parse_topic("some/other/topic") is None
