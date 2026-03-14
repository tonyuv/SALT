"""Kafka-to-PostgreSQL sink.

Consumes all telemetry Kafka topics and writes to PostgreSQL tables.
"""

import json
import logging
import sys
import time

import psycopg2
import psycopg2.extras
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.admin import AdminClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("postgres-sink")

KAFKA_BOOTSTRAP = "kafka:29092"
PG_DSN = "host=postgres port=5432 dbname=salt user=salt password=salt"
MAX_RETRIES = 120
RETRY_DELAY = 3
BATCH_SIZE = 50
FLUSH_INTERVAL = 2.0  # seconds

TELEMETRY_TOPICS = [
    "kafka-topic-temperature",
    "kafka-topic-humidity",
    "kafka-topic-oil-temp",
    "kafka-topic-battery-voltage",
    "kafka-topic-tire-pressure",
    "kafka-topic-fuel-level",
    "kafka-topic-speed",
    "kafka-topic-rpm",
    "kafka-topic-transmission-temp",
    "kafka-topic-brakepad-wear",
]
CONN_TOPIC = "kafka-topic-connection-status"
AGENT_TOPIC = "kafka-topic-agent-logs"

ALL_TOPICS = TELEMETRY_TOPICS + [CONN_TOPIC, AGENT_TOPIC]


def wait_for_kafka():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Probing Kafka (attempt %d/%d)", attempt, MAX_RETRIES)
            admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})
            admin.list_topics(timeout=5)
            logger.info("Kafka is reachable.")
            return
        except Exception as exc:
            logger.warning("Kafka not ready: %s", exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    logger.critical("Kafka unavailable. Exiting.")
    sys.exit(1)


def wait_for_postgres() -> psycopg2.extensions.connection:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Connecting to PostgreSQL (attempt %d/%d)", attempt, MAX_RETRIES)
            conn = psycopg2.connect(PG_DSN)
            conn.autocommit = False
            logger.info("PostgreSQL connected.")
            return conn
        except psycopg2.OperationalError as exc:
            logger.warning("PostgreSQL not ready: %s", exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    logger.critical("PostgreSQL unavailable. Exiting.")
    sys.exit(1)


def flush_telemetry(cur, batch: list[dict]):
    if not batch:
        return
    rows = []
    for d in batch:
        rows.append((
            d.get("sensor_id", ""),
            d.get("vin", ""),
            d.get("manufacturer", ""),
            d.get("vehicle", ""),
            d.get("value", 0),
            d.get("unit", ""),
            d.get("label", ""),
            d.get("kafka_topic", ""),
            d.get("timestamp", ""),
        ))
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO telemetry_readings (sensor_id, vin, manufacturer, vehicle, value, unit, label, kafka_topic, ts)
           VALUES %s""",
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )


def flush_connections(cur, batch: list[dict]):
    if not batch:
        return
    rows = []
    for d in batch:
        rows.append((
            d.get("sensor_id", ""),
            d.get("vin", ""),
            d.get("manufacturer", ""),
            d.get("vehicle", ""),
            d.get("label", ""),
            d.get("event", ""),
            d.get("timestamp", ""),
        ))
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO connection_events (sensor_id, vin, manufacturer, vehicle, label, event, ts)
           VALUES %s""",
        rows,
        template="(%s, %s, %s, %s, %s, %s, %s)",
    )


def flush_agent_logs(cur, batch: list[dict]):
    if not batch:
        return
    rows = []
    for d in batch:
        rows.append((
            d.get("level", ""),
            d.get("component", ""),
            d.get("message", ""),
            d.get("timestamp", ""),
        ))
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO agent_logs (level, component, message, ts)
           VALUES %s""",
        rows,
        template="(%s, %s, %s, %s)",
    )


def main():
    wait_for_kafka()
    pg_conn = wait_for_postgres()

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": "postgres-sink",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })
    consumer.subscribe(ALL_TOPICS)
    logger.info("Subscribed to %d Kafka topics. Sinking to PostgreSQL.", len(ALL_TOPICS))

    telemetry_batch: list[dict] = []
    conn_batch: list[dict] = []
    agent_batch: list[dict] = []
    last_flush = time.monotonic()
    total_rows = 0

    try:
        while True:
            msg = consumer.poll(timeout=0.3)

            if msg is not None and not msg.error():
                try:
                    data = json.loads(msg.value().decode("utf-8"))
                    data["kafka_topic"] = msg.topic()

                    if msg.topic() == CONN_TOPIC:
                        conn_batch.append(data)
                    elif msg.topic() == AGENT_TOPIC:
                        agent_batch.append(data)
                    else:
                        telemetry_batch.append(data)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            elif msg is not None and msg.error() and msg.error().code() != KafkaError._PARTITION_EOF:
                logger.error("Consumer error: %s", msg.error())

            # Flush on batch size or time interval
            batch_total = len(telemetry_batch) + len(conn_batch) + len(agent_batch)
            elapsed = time.monotonic() - last_flush

            if batch_total >= BATCH_SIZE or (batch_total > 0 and elapsed >= FLUSH_INTERVAL):
                try:
                    cur = pg_conn.cursor()
                    flush_telemetry(cur, telemetry_batch)
                    flush_connections(cur, conn_batch)
                    flush_agent_logs(cur, agent_batch)
                    pg_conn.commit()
                    total_rows += batch_total
                    if total_rows % 500 < batch_total:
                        logger.info("Sunk %d rows total (%d telemetry, %d conn, %d agent in batch)",
                                    total_rows, len(telemetry_batch), len(conn_batch), len(agent_batch))
                    cur.close()
                except psycopg2.Error as exc:
                    logger.error("PostgreSQL write failed: %s", exc)
                    pg_conn.rollback()
                    # Reconnect
                    try:
                        pg_conn.close()
                    except Exception:
                        pass
                    pg_conn = wait_for_postgres()

                telemetry_batch.clear()
                conn_batch.clear()
                agent_batch.clear()
                last_flush = time.monotonic()

    except KeyboardInterrupt:
        logger.info("Shutting down postgres sink.")
    finally:
        consumer.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
