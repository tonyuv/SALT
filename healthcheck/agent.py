"""SALT infrastructure health-check agent.

Runs inside Docker, checks all services every 30s, and publishes
structured log entries to /telemetry/agent_logs via MQTT.
"""

import json
import logging
import random
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("healthcheck-agent")

BROKER_HOST = "emqx"
BROKER_PORT = 1883
KAFKA_HOST = "kafka"
KAFKA_PORT = 29092
TOPIC = "/telemetry/agent_logs"
CHECK_INTERVAL = 30
MAX_RETRIES = 120
RETRY_DELAY = 3


def check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def run_checks() -> list[dict]:
    """Run all health checks and return a list of log entries."""
    entries = []
    now = datetime.now(timezone.utc).isoformat()

    # 1. EMQX reachability
    emqx_ok = check_tcp(BROKER_HOST, BROKER_PORT)
    entries.append({
        "timestamp": now,
        "level": "OK" if emqx_ok else "CRITICAL",
        "component": "EMQX",
        "message": f"MQTT broker {'reachable' if emqx_ok else 'UNREACHABLE'} on {BROKER_HOST}:{BROKER_PORT}",
    })

    # 2. Kafka reachability
    kafka_ok = check_tcp(KAFKA_HOST, KAFKA_PORT)
    entries.append({
        "timestamp": now,
        "level": "OK" if kafka_ok else "CRITICAL",
        "component": "Kafka",
        "message": f"Kafka broker {'reachable' if kafka_ok else 'UNREACHABLE'} on {KAFKA_HOST}:{KAFKA_PORT}",
    })

    # 3. Kafka topic count via AdminClient
    topic_count = 0
    try:
        from confluent_kafka.admin import AdminClient
        admin = AdminClient({"bootstrap.servers": f"{KAFKA_HOST}:{KAFKA_PORT}"})
        topics = admin.list_topics(timeout=5).topics
        topic_count = len([t for t in topics if not t.startswith("_")])
        ok = topic_count >= 11
        entries.append({
            "timestamp": now,
            "level": "OK" if ok else "WARN",
            "component": "Kafka Topics",
            "message": f"{topic_count} user topics found (expected 11)",
        })
    except Exception as exc:
        entries.append({
            "timestamp": now,
            "level": "ERROR",
            "component": "Kafka Topics",
            "message": f"Failed to list topics: {exc}",
        })

    # 4. Zookeeper reachability
    zk_ok = check_tcp("zookeeper", 2181)
    entries.append({
        "timestamp": now,
        "level": "OK" if zk_ok else "CRITICAL",
        "component": "Zookeeper",
        "message": f"Zookeeper {'reachable' if zk_ok else 'UNREACHABLE'} on :2181",
    })

    # 5. Dashboard reachability
    dash_ok = check_tcp("web-dashboard", 8080)
    entries.append({
        "timestamp": now,
        "level": "OK" if dash_ok else "WARN",
        "component": "Dashboard",
        "message": f"Web dashboard {'responding' if dash_ok else 'NOT RESPONDING'} on :8080",
    })

    # 6. Summary
    issues = [e for e in entries if e["level"] != "OK"]
    if issues:
        summary = f"{len(issues)} issue(s) detected: {', '.join(e['component'] for e in issues)}"
        level = "CRITICAL" if any(e["level"] == "CRITICAL" for e in issues) else "WARN"
    else:
        summary = f"All systems healthy. EMQX up, Kafka up ({topic_count} topics), ZK up, Dashboard up."
        level = "OK"

    entries.append({
        "timestamp": now,
        "level": level,
        "component": "Agent Summary",
        "message": summary,
    })

    return entries


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"healthcheck-agent-{random.randint(1000, 9999)}",
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            return client
        except (ConnectionRefusedError, OSError) as exc:
            logger.warning("MQTT connect attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.critical("Could not connect to MQTT. Exiting.")
    sys.exit(1)


def main() -> None:
    # Wait for infrastructure to come up
    logger.info("Health-check agent starting, waiting for EMQX...")
    time.sleep(10)

    client = connect_mqtt()
    client.loop_start()
    logger.info("Health-check agent connected. Checking every %ds.", CHECK_INTERVAL)

    try:
        while True:
            entries = run_checks()
            for entry in entries:
                payload = json.dumps(entry)
                client.publish(TOPIC, payload, qos=1)

            summary = entries[-1]
            logger.info("[%s] %s", summary["level"], summary["message"])
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Health-check agent stopping.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
