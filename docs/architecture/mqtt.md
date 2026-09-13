# MQTT

## What ICAB uses

`icab.context.mqtt` (added in the M3 milestone) adds MQTT as a first-class
ICAB context/data source, backed by a local [Eclipse
Mosquitto](https://mosquitto.org/) broker (`mqtt_broker` in
`docker-compose.yml`, config at `services/mqtt/mosquitto.conf`) and the
[`paho-mqtt`](https://pypi.org/project/paho-mqtt/) client library.

## Topic namespace

Topics are built as `icab/<domain>/<equipment-key>/<measurement>`, e.g.
`icab/tep/reactor/reactor_pressure` (see `icab.context.mqtt.topics`). This
mirrors the site/equipment/measurement shape ICAB's UNS paths already use
(`site/tep/reaction/reactor/pressure`), anchored to the real-simulator
equipment registry introduced in M2 (`icab.tep.measurements.REAL_TEP_EQUIPMENT`)
rather than an invented hierarchy.

## Message shape

Every `MQTTMessage` (`icab.context.mqtt.models`) preserves timestamp, source,
topic, value, unit (where available), quality (where available), and
canonical ID (where available), per the ICAB message-provenance rules.
Messages are published with `retain=True` by default, so a client that
`discover()`s or `read()`s a topic gets the last known value immediately
without waiting for the next publish cycle -- the same "ask the channel"
interaction pattern a real MQTT-based UNS client would use.

## Design choice: one-shot discover/read vs. a persistent subscriber

`MQTTClient` supports two patterns:

- **Persistent publishing** (`connect()` / `publish()` / `disconnect()`, or
  `with client:`) -- used by `TEPMeasurementPublisher` to stream simulator
  measurements.
- **One-shot discovery/read** (`discover(topic_filter)` / `read(topic)`) --
  used by the Agent Gateway's `browse_mqtt`/`read_mqtt` tools. Each call
  opens its own short-lived subscription, collects whatever is retained on
  matching topics for a bounded `timeout`, and disconnects.

A persistent background subscriber maintaining a live in-memory cache inside
the gateway process was considered and rejected for this milestone: it would
need explicit lifecycle management (thread startup/shutdown tied to the
FastAPI app, reconnect-on-drop logic) for a benefit -- avoiding the
`discover()` timeout latency -- that does not matter yet at ICAB's current
scale. The one-shot approach keeps the gateway stateless and is simple to
reason about and test; it can be replaced with a persistent subscriber later
without changing the `browse_mqtt`/`read_mqtt` tool contracts if latency
becomes a real constraint.

## Research property this preserves

The gateway does not hand the agent a preassembled context dictionary for
MQTT: `browse_mqtt` performs real topic discovery over the broker, and
`read_mqtt` performs a real subscribe-and-wait read. An agent using the MQTT
architecture is exercising an actual industrial messaging channel, with the
same discovery/latency characteristics that channel has in practice.
