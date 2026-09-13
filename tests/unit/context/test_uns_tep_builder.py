from icab.context.uns.repository import InMemoryUNSRepository
from icab.context.uns.service import UNSService
from icab.context.uns.tep_builder import build_real_uns_nodes


def test_build_real_uns_nodes_includes_site_equipment_and_measurements():
    nodes = build_real_uns_nodes()

    by_path = {node.path: node for node in nodes}

    assert "site/tep" in by_path
    assert by_path["site/tep"].node_type == "site"

    assert "site/tep/reactor" in by_path
    assert by_path["site/tep/reactor"].node_type == "equipment"
    assert by_path["site/tep/reactor"].canonical_id == "urn:icab:equipment:reactor"

    assert "site/tep/reactor/reactor_pressure" in by_path
    assert by_path["site/tep/reactor/reactor_pressure"].node_type == "measurement"
    assert (
        by_path["site/tep/reactor/reactor_pressure"].canonical_id
        == "urn:icab:measurement:reactor_pressure"
    )

    # 1 site + 7 equipment + 41 measurements + 12 actuators (M13-A)
    assert len(nodes) == 1 + 7 + 41 + 12


def test_build_real_uns_nodes_includes_actuators():
    nodes = build_real_uns_nodes()

    by_path = {node.path: node for node in nodes}

    assert "site/tep/reactor/reactor_cooling_water_valve" in by_path
    actuator = by_path["site/tep/reactor/reactor_cooling_water_valve"]
    assert actuator.node_type == "actuator"
    assert actuator.canonical_id == "urn:icab:actuator:reactor_cooling_water_valve"


def test_build_real_uns_nodes_are_browsable():
    nodes = build_real_uns_nodes()
    service = UNSService(InMemoryUNSRepository(nodes))

    equipment = service.browse("site/tep")
    equipment_paths = {node.path for node in equipment}

    assert "site/tep/reactor" in equipment_paths
    assert "site/tep/separator" in equipment_paths

    reactor_measurements = service.browse("site/tep/reactor")
    measurement_names = {node.display_name for node in reactor_measurements}

    assert "Reactor pressure" in measurement_names
    assert "Reactor level" in measurement_names
    assert "Reactor temperature" in measurement_names
