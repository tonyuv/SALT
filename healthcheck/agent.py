"""SALT infrastructure health-check agent with AI analysis.

Runs inside Docker, checks all services every 30s, optionally sends results
to Claude API for intelligent analysis, and publishes structured log entries
to /telemetry/agent_logs via MQTT.

Requirements:
  - ANTHROPIC_API_KEY env var set for AI analysis (optional — falls back to
    rule-based summaries if unset)
"""

import json
import logging
import os
import random
import socket
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

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_ENABLED = bool(ANTHROPIC_API_KEY)


# ── Infrastructure checks ─────────────────────────────────────────────────────

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

    return entries


# ── AI analysis ────────────────────────────────────────────────────────────────

def get_ai_analysis(entries: list[dict]) -> str | None:
    """Send check results to Claude API for intelligent analysis.

    Returns the AI's analysis string, or None if AI is disabled or fails.
    """
    if not AI_ENABLED:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        checks_text = "\n".join(
            f"[{e['level']}] {e['component']}: {e['message']}" for e in entries
        )

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": f"""You are a SALT infrastructure health-check agent monitoring a fleet telemetry pipeline.
Analyze these check results and provide a brief (2-3 sentence) summary. If there are issues,
suggest specific remediation steps (e.g. docker compose commands). If everything is healthy,
note any patterns or observations worth tracking.

Check results:
{checks_text}

Respond with only the analysis, no preamble."""
            }],
        )
        return message.content[0].text
    except Exception as exc:
        logger.warning("AI analysis failed: %s", exc)
        return None


def build_summary(entries: list[dict], ai_analysis: str | None) -> dict:
    """Build the summary log entry, using AI analysis if available."""
    now = datetime.now(timezone.utc).isoformat()
    issues = [e for e in entries if e["level"] != "OK"]

    if issues:
        level = "CRITICAL" if any(e["level"] == "CRITICAL" for e in issues) else "WARN"
    else:
        level = "OK"

    if ai_analysis:
        message = ai_analysis
        component = "AI Agent Summary"
    else:
        if issues:
            message = f"{len(issues)} issue(s) detected: {', '.join(e['component'] for e in issues)}"
        else:
            topic_entry = next((e for e in entries if e["component"] == "Kafka Topics"), None)
            topic_count = topic_entry["message"].split()[0] if topic_entry else "?"
            message = f"All systems healthy. EMQX up, Kafka up ({topic_count} topics), ZK up, Dashboard up."
        component = "Agent Summary"

    return {
        "timestamp": now,
        "level": level,
        "component": component,
        "message": message,
    }


# ── MQTT ───────────────────────────────────────────────────────────────────────

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


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("Health-check agent starting, waiting for EMQX...")
    logger.info("AI analysis: %s", "ENABLED (Claude Haiku)" if AI_ENABLED else "DISABLED (no ANTHROPIC_API_KEY)")
    time.sleep(10)

    client = connect_mqtt()
    client.loop_start()
    logger.info("Health-check agent connected. Checking every %ds.", CHECK_INTERVAL)

    try:
        while True:
            entries = run_checks()

            # Get AI analysis (returns None if disabled or fails)
            ai_analysis = get_ai_analysis(entries)

            # Build summary (AI-powered or rule-based fallback)
            summary = build_summary(entries, ai_analysis)
            entries.append(summary)

            # Publish all entries to MQTT
            for entry in entries:
                payload = json.dumps(entry)
                client.publish(TOPIC, payload, qos=1)

            logger.info("[%s] %s", summary["level"], summary["message"])
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Health-check agent stopping.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
