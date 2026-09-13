from icab.tep.measurements import TEPVariable, build_real_tep_variables
from icab.tep.simulator import TEPSimulator

from .client import MQTTClient
from .models import MQTTMessage
from .topics import build_topic, equipment_key_from_canonical_id


class TEPMeasurementPublisher:
    """
    Bridges a :class:`~icab.tep.simulator.TEPSimulator`'s measurements onto
    the ICAB MQTT namespace, so an agent can acquire simulator state through
    an industrial messaging channel rather than a preassembled dictionary.
    """

    DOMAIN = "tep"

    def __init__(self, client: MQTTClient, *, source: str = "tep-simulator") -> None:
        self.client = client
        self.source = source
        self._variables_by_id: dict[str, TEPVariable] = {
            variable.variable_id: variable for variable in build_real_tep_variables()
        }

    def topic_for(self, variable_id: str) -> str:
        """Return the MQTT topic a given real-measurement variable id publishes to."""

        variable = self._variables_by_id[variable_id]
        equipment_key = equipment_key_from_canonical_id(variable.equipment_id)
        return build_topic(self.DOMAIN, equipment_key, variable_id.lower())

    def publish_state(
        self,
        simulator: TEPSimulator,
        *,
        qos: int = 0,
        retain: bool = True,
    ) -> list[str]:
        """
        Publish the simulator's current measurements to MQTT.

        Requires an already-connected ``client`` (e.g. used inside
        ``with client:``). Returns the list of topics published to.
        """

        state = simulator.get_state()
        published = []

        for variable_id, value in state.values.items():
            variable = self._variables_by_id.get(variable_id)

            if variable is None:
                # Not a real-simulator measurement (e.g. a legacy prototype
                # variable_id) -- nothing to publish for it here.
                continue

            message = MQTTMessage(
                topic=self.topic_for(variable_id),
                timestamp=state.timestamp,
                source=self.source,
                value=value,
                unit=variable.unit,
                quality="GOOD",
                canonical_id=variable.canonical_id,
            )

            self.client.publish(message, qos=qos, retain=retain)
            published.append(message.topic)

        return published
