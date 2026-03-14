"""MQTT-to-Kafka bridge.

Subscribes to ``/telemetry/#`` on EMQX and forwards every message to the
matching Kafka topic. Creates all topics on startup if they do not already exist.
"""

import json
import logging
import sys
import time

import paho.mqtt.client as mqtt
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mqtt-kafka-bridge")

# ── Configuration ──────────────────────────────────────────────────────────────
MQTT_BROKER = "emqx"
MQTT_PORT = 1883
MQTT_TOPIC = "/telemetry/#"

KAFKA_BOOTSTRAP = "kafka:29092"

# Map the last path-segment of the MQTT topic to a Kafka topic name.
TOPIC_MAP = {
    "temperature": "kafka-topic-temperature",
    "humidity": "kafka-topic-humidity",
    "oil_temp": "kafka-topic-oil-temp",
    "battery_voltage": "kafka-topic-battery-voltage",
    "tire_pressure": "kafka-topic-tire-pressure",
    "fuel_level": "kafka-topic-fuel-level",
    "speed": "kafka-topic-speed",
    "rpm": "kafka-topic-rpm",
    "transmission_temp": "kafka-topic-transmission-temp",
    "brakepad_wear": "kafka-topic-brakepad-wear",
    "connection_status": "kafka-topic-connection-status",
    "agent_logs": "kafka-topic-agent-logs",
}

MAX_RETRIES = 60
RETRY_DELAY = 3


# ── Kafka helpers ──────────────────────────────────────────────────────────────

def wait_for_kafka() -> AdminClient:
    admin_conf = {"bootstrap.servers": KAFKA_BOOTSTRAP}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Probing Kafka at %s (attempt %d/%d)", KAFKA_BOOTSTRAP, attempt, MAX_RETRIES)
            admin = AdminClient(admin_conf)
            admin.list_topics(timeout=5)
            logger.info("Kafka is reachable.")
            return admin
        except Exception as exc:
            logger.warning("Kafka not ready: %s", exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.critical("Kafka not available after %d attempts. Exiting.", MAX_RETRIES)
    sys.exit(1)


def ensure_topics(admin: AdminClient) -> None:
    existing = set(admin.list_topics(timeout=10).topics.keys())
    to_create = []
    for kafka_topic in TOPIC_MAP.values():
        if kafka_topic not in existing:
            to_create.append(NewTopic(kafka_topic, num_partitions=3, replication_factor=1))

    if not to_create:
        logger.info("All %d Kafka topics already exist.", len(TOPIC_MAP))
        return

    logger.info("Creating Kafka topics: %s", [t.topic for t in to_create])
    futures = admin.create_topics(to_create)
    for topic, future in futures.items():
        try:
            future.result()
            logger.info("Created topic: %s", topic)
        except Exception as exc:
            logger.warning("Topic creation for %s returned: %s", topic, exc)


def create_producer() -> Producer:
    return Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "acks": "all",
        "retries": 5,
        "retry.backoff.ms": 500,
        "linger.ms": 10,
        "batch.num.messages": 100,
    })


def delivery_callback(err, msg):
    if err is not None:
        logger.error("Kafka delivery failed for %s: %s", msg.topic(), err)


# ── MQTT helpers ───────────────────────────────────────────────────────────────

def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="mqtt-kafka-bridge",
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Connecting to MQTT %s:%d (attempt %d/%d)", MQTT_BROKER, MQTT_PORT, attempt, MAX_RETRIES)
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            logger.info("Connected to MQTT broker.")
            return client
        except (ConnectionRefusedError, OSError) as exc:
            logger.warning("MQTT connection attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.critical("Could not connect to MQTT after %d attempts. Exiting.", MAX_RETRIES)
    sys.exit(1)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    admin = wait_for_kafka()
    ensure_topics(admin)
    producer = create_producer()

    mqtt_client = connect_mqtt()

    msg_count = 0

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        if reason_code == 0:
            logger.info("MQTT connected -- subscribing to %s", MQTT_TOPIC)
            _client.subscribe(MQTT_TOPIC, qos=1)
        else:
            logger.error("MQTT connect failed: %s", reason_code)

    def on_message(_client, _userdata, msg: mqtt.MQTTMessage):
        nonlocal msg_count
        topic_segment = msg.topic.rsplit("/", 1)[-1]
        kafka_topic = TOPIC_MAP.get(topic_segment)
        if kafka_topic is None:
            logger.warning("No Kafka mapping for MQTT topic segment '%s' (full: %s)", topic_segment, msg.topic)
            return

        try:
            payload = msg.payload.decode("utf-8")
            json.loads(payload)  # validate
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error("Invalid message payload on %s: %s", msg.topic, exc)
            return

        producer.produce(
            kafka_topic,
            value=payload.encode("utf-8"),
            callback=delivery_callback,
        )
        producer.poll(0)

        msg_count += 1
        if msg_count % 100 == 0:
            logger.info("Bridged %d messages total (latest: %s -> %s)", msg_count, msg.topic, kafka_topic)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    logger.info("Bridge running with %d topic mappings. Ctrl+C to stop.", len(TOPIC_MAP))

    try:
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down bridge.")
    finally:
        producer.flush(timeout=10)
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
