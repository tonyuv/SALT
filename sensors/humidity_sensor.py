"""BMDoubleYou cabin humidity sensor simulator.

Models realistic cabin humidity based on weather conditions, HVAC state,
window events, and passenger breathing. Includes simulated broker disconnects.
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from enum import Enum

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("bmdoubleyou.cabin-humidity")

BROKER_HOST = "emqx"
BROKER_PORT = 1883
TOPIC = "/telemetry/humidity"
SENSOR_ID = "bmdu-cabin-hum-3A91"
VEHICLE_VIN = "WBMDU93051CZ00742"

MAX_RETRIES = 120
RETRY_DELAY = 3


# ── Cabin humidity model ──────────────────────────────────────────────────────

class HvacMode(Enum):
    OFF = "off"
    AC_LOW = "ac_low"
    AC_HIGH = "ac_high"
    HEAT = "heat"
    DEFOG = "defog"


class CabinHumidityModel:
    """Simulates realistic cabin humidity behaviour.

    - Ambient outdoor humidity sets the baseline (40-85%)
    - HVAC cycles reduce humidity (AC) or leave it alone (heat)
    - Window-open events let outside air in
    - Passenger breathing gradually increases humidity
    - HVAC mode changes every 40-80 ticks
    """

    def __init__(self):
        self.outdoor_humidity = random.uniform(40.0, 85.0)
        self.humidity = self.outdoor_humidity + random.uniform(-5, 5)
        self.hvac = random.choice(list(HvacMode))
        self.hvac_change_tick = random.randint(40, 80)
        self.window_open = False
        self.window_event_tick = random.randint(60, 150)
        self.tick = 0
        self.passengers = random.randint(1, 4)

    def step(self) -> float:
        self.tick += 1

        # HVAC mode change
        if self.tick >= self.hvac_change_tick:
            old = self.hvac
            self.hvac = random.choice(list(HvacMode))
            self.hvac_change_tick = self.tick + random.randint(40, 80)
            if self.hvac != old:
                logger.info("HVAC mode changed: %s -> %s", old.value, self.hvac.value)

        # Window events
        if self.tick >= self.window_event_tick:
            self.window_open = not self.window_open
            self.window_event_tick = self.tick + random.randint(30, 100)
            logger.info("Window %s", "opened" if self.window_open else "closed")

        # Drift toward target based on conditions
        target = self._target_humidity()
        drift_rate = 0.08 if not self.window_open else 0.2
        drift = (target - self.humidity) * drift_rate

        # Passenger breathing adds ~0.1-0.3% per tick
        breath = self.passengers * random.uniform(0.05, 0.15)

        # Sensor noise
        noise = random.gauss(0, 0.25)

        self.humidity += drift + breath + noise
        self.humidity = max(15.0, min(95.0, self.humidity))

        return round(self.humidity, 2)

    def _target_humidity(self) -> float:
        if self.window_open:
            return self.outdoor_humidity
        if self.hvac == HvacMode.AC_HIGH:
            return 30.0
        if self.hvac == HvacMode.AC_LOW:
            return 40.0
        if self.hvac == HvacMode.DEFOG:
            return 25.0
        if self.hvac == HvacMode.HEAT:
            return 35.0
        return self.outdoor_humidity  # OFF


# ── Disconnect simulator ──────────────────────────────────────────────────────

class DisconnectSimulator:
    def __init__(self):
        self.base_interval = 3.0
        self.next_disconnect_tick = random.randint(40, 130)
        self.tick = 0
        self.disconnected = False
        self.reconnect_at_tick = 0

    def should_disconnect(self) -> bool:
        self.tick += 1
        if not self.disconnected and self.tick >= self.next_disconnect_tick:
            self.disconnected = True
            outage = random.randint(2, 8)
            self.reconnect_at_tick = self.tick + outage
            logger.warning("Simulating broker disconnect for ~%d s", outage * 3)
            return True
        return False

    def should_reconnect(self) -> bool:
        if self.disconnected and self.tick >= self.reconnect_at_tick:
            self.disconnected = False
            self.next_disconnect_tick = self.tick + random.randint(40, 130)
            return True
        return False

    def jittered_interval(self) -> float:
        return self.base_interval + random.uniform(-0.5, 1.0)


# ── MQTT ──────────────────────────────────────────────────────────────────────

def connect_with_retry() -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{SENSOR_ID}-{random.randint(1000, 9999)}",
    )

    def on_connect(_c, _u, _f, rc, _p):
        if rc == 0:
            logger.info("Connected to MQTT broker at %s:%d", BROKER_HOST, BROKER_PORT)
        else:
            logger.error("Connection failed (rc=%s)", rc)

    def on_disconnect(_c, _u, _f, rc, _p):
        logger.warning("Disconnected from broker (rc=%s)", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Connecting to %s:%d (attempt %d/%d)",
                        BROKER_HOST, BROKER_PORT, attempt, MAX_RETRIES)
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            return client
        except (ConnectionRefusedError, OSError) as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.critical("Could not connect after %d attempts. Exiting.", MAX_RETRIES)
    sys.exit(1)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    client = connect_with_retry()
    client.loop_start()

    model = CabinHumidityModel()
    disc = DisconnectSimulator()

    logger.info("BMDoubleYou cabin humidity sensor [%s] VIN=%s — publishing to %s",
                SENSOR_ID, VEHICLE_VIN, TOPIC)

    try:
        while True:
            if disc.should_disconnect():
                client.disconnect()
            elif disc.should_reconnect():
                logger.info("Simulated reconnect — re-establishing connection")
                client.reconnect()

            humidity = model.step()

            if not disc.disconnected:
                reading = {
                    "sensor_id": SENSOR_ID,
                    "vin": VEHICLE_VIN,
                    "vehicle": "BMDoubleYou 5-Series",
                    "value": humidity,
                    "unit": "%",
                    "label": "cabin_humidity",
                    "hvac_mode": model.hvac.value,
                    "window_open": model.window_open,
                    "passengers": model.passengers,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                payload = json.dumps(reading)
                result = client.publish(TOPIC, payload, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("Published: %.1f%% [hvac=%s, window=%s]",
                                humidity, model.hvac.value, model.window_open)
                else:
                    logger.error("Publish failed (rc=%d)", result.rc)
            else:
                logger.debug("Skipping publish — simulated disconnect active")

            time.sleep(disc.jittered_interval())

    except KeyboardInterrupt:
        logger.info("Shutting down cabin humidity sensor.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
