from unittest.mock import Mock

from icab.cim import CIMEnvironment
from icab.context.environment_loader import EnvironmentLoader
from icab.context.mqtt import TEPMeasurementPublisher
from icab.tep import TEPAdapter, TEPContextSync, TEPSimulator


def test_sync_loads_the_real_environment_into_historian_and_kg():
    loader = Mock(spec=EnvironmentLoader)

    simulator = TEPSimulator()
    simulator.reset(seed=1)

    sync = TEPContextSync(environment_loader=loader)
    environment = sync.sync(simulator)

    assert isinstance(environment, CIMEnvironment)
    assert len(environment.observations) == 41

    loader.load.assert_called_once_with(environment)


def test_sync_publishes_to_mqtt_when_configured():
    loader = Mock(spec=EnvironmentLoader)
    publisher = Mock(spec=TEPMeasurementPublisher)

    simulator = TEPSimulator()
    simulator.reset(seed=1)

    sync = TEPContextSync(environment_loader=loader, mqtt_publisher=publisher)
    sync.sync(simulator)

    publisher.publish_state.assert_called_once_with(simulator)


def test_sync_does_not_require_mqtt():
    loader = Mock(spec=EnvironmentLoader)

    simulator = TEPSimulator()
    simulator.reset(seed=1)

    sync = TEPContextSync(environment_loader=loader)

    # Should not raise even though no mqtt_publisher was configured.
    sync.sync(simulator)


def test_sync_uses_the_provided_adapter():
    loader = Mock(spec=EnvironmentLoader)
    adapter = Mock(spec=TEPAdapter)
    adapter.build_real_environment.return_value = CIMEnvironment()

    simulator = TEPSimulator()
    simulator.reset(seed=1)

    sync = TEPContextSync(environment_loader=loader, adapter=adapter)
    environment = sync.sync(simulator)

    adapter.build_real_environment.assert_called_once()
    assert environment == CIMEnvironment()
