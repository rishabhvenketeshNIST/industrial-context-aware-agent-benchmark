from __future__ import annotations

import json
import time
from types import TracebackType

import paho.mqtt.client as paho

from .models import MQTTMessage


class MQTTClient:
    """
    Thin ICAB wrapper around a paho-mqtt client.

    Two usage patterns are supported:

    * **Persistent publishing** -- ``connect()`` once, ``publish(...)`` many
      times (e.g. a simulator streaming measurements), then ``disconnect()``
      (or use as a context manager: ``with client: ...``).
    * **One-shot discovery/read** -- :meth:`discover` and :meth:`read` open
      their own short-lived connection, collect any messages retained on
      matching topics, and disconnect. This is what the ICAB gateway uses:
      an agent "discovers" or "reads" information over the MQTT channel
      itself, rather than receiving a preassembled context dictionary.
    """

    def __init__(
        self,
        host: str,
        port: int = 1883,
        *,
        client_id: str = "",
        keepalive: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.keepalive = keepalive
        self._client: paho.Client | None = None

    # -- persistent connection (publishing) ------------------------------

    def connect(self) -> None:
        client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
        )
        client.connect(self.host, self.port, self.keepalive)
        client.loop_start()
        self._client = client

    def disconnect(self) -> None:
        if self._client is None:
            return

        self._client.loop_stop()
        self._client.disconnect()
        self._client = None

    def publish(
        self,
        message: MQTTMessage,
        *,
        qos: int = 0,
        retain: bool = True,
    ) -> None:
        if self._client is None:
            raise RuntimeError("MQTTClient.connect() must be called before publish().")

        payload = json.dumps(message.model_dump(mode="json"))
        info = self._client.publish(message.topic, payload, qos=qos, retain=retain)
        # Ensure the message has actually left the local send queue before
        # returning -- important for callers that publish() then immediately
        # disconnect() (e.g. `with client: client.publish(...)`).
        info.wait_for_publish(timeout=5.0)

    def __enter__(self) -> "MQTTClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()

    # -- one-shot discovery / read ---------------------------------------

    def discover(
        self,
        topic_filter: str = "icab/#",
        *,
        timeout: float = 1.0,
    ) -> list[MQTTMessage]:
        """
        Subscribe to ``topic_filter`` for ``timeout`` seconds and return every
        (deduplicated, latest-per-topic) message observed -- in particular,
        any value the broker has retained for a matching topic.
        """

        collected: dict[str, MQTTMessage] = {}
        parse_error_count = 0

        def _on_message(
            client: paho.Client,
            userdata: object,
            msg: paho.MQTTMessage,
        ) -> None:
            nonlocal parse_error_count

            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                message = MQTTMessage.model_validate({**payload, "topic": msg.topic})
            except Exception:
                parse_error_count += 1
                return

            collected[msg.topic] = message

        client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id="",
            clean_session=True,
        )
        client.on_message = _on_message
        client.connect(self.host, self.port, self.keepalive)
        client.subscribe(topic_filter, qos=0)
        client.loop_start()

        try:
            time.sleep(timeout)
        finally:
            client.loop_stop()
            client.disconnect()

        return sorted(collected.values(), key=lambda message: message.topic)

    def read(self, topic: str, *, timeout: float = 1.0) -> MQTTMessage | None:
        """Return the (retained) message on a single, fully-qualified topic."""

        messages = self.discover(topic, timeout=timeout)
        return messages[0] if messages else None
