import pytest

from icab.agent.llm.tools import ARCHITECTURE_TOOL_NAMES
from icab.experiments.architecture_combinations import (
    ARCHITECTURE_COMBINATIONS,
    get_combination,
    list_combination_keys,
)


def test_at_least_the_eight_requested_combinations_exist():
    assert len(ARCHITECTURE_COMBINATIONS) >= 8


def test_every_combination_uses_only_known_architecture_names():
    for combination in ARCHITECTURE_COMBINATIONS:
        for architecture in combination.architectures:
            assert architecture in ARCHITECTURE_TOOL_NAMES, (
                f"{combination.key} references unknown architecture {architecture!r}"
            )


def test_every_combination_has_a_nonempty_rationale():
    for combination in ARCHITECTURE_COMBINATIONS:
        assert combination.rationale.strip()


def test_combination_keys_are_unique():
    keys = [combination.key for combination in ARCHITECTURE_COMBINATIONS]
    assert len(keys) == len(set(keys))


def test_full_combination_covers_every_architecture():
    full = get_combination("full")
    assert set(full.architectures) == set(ARCHITECTURE_TOOL_NAMES)


def test_get_combination_by_key():
    combo = get_combination("historian_only")
    assert combo.architectures == ("historian",)


def test_get_unknown_combination_raises_with_valid_keys_listed():
    with pytest.raises(KeyError, match="historian_only"):
        get_combination("not_a_real_combination")


def test_list_combination_keys_is_sorted_and_matches_registry():
    keys = list_combination_keys()
    assert keys == sorted(keys)
    assert set(keys) == {combination.key for combination in ARCHITECTURE_COMBINATIONS}


def test_mqtt_uns_historian_has_no_relational_layer():
    """This combination was chosen specifically to produce redundant
    acquisition without a KG available to explain it."""
    combo = get_combination("mqtt_uns_historian")
    assert "knowledge_graph" not in combo.architectures
    assert "mqtt" in combo.architectures and "historian" in combo.architectures
