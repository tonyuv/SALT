"""BMDoubleYou engine coolant temperature sensor simulator.

Models a realistic engine warm-up curve (ambient → operating temp), steady-state
drift, occasional thermostat spikes, and random broker disconnects to simulate
real-world vehicle telemetry over MQTT.
"""

import json
import logging
import math
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
logger = logging.getLogger("bmdoubleyou.coolant-temp")

BROKER_HOST = "emqx"
BROKER_PORT = 1883
TOPIC = "/telemetry/temperature"
SENSOR_ID = "bmdu-coolant-temp-7F28"
VEHICLE_VIN = "WBMDU93051CZ00742"

MAX_RETRIES = 120
RETRY_DELAY = 3


# ── Engine thermal model ──────────────────────────────────────────────────────

class EnginePhase(Enum):
    COLD_START = "cold_start"
    WARM_UP = "warm_up"
    OPERATING = "operating"
    HOT_SOAK = "hot_soak"


class CoolantTempModel:
    """Simulates realistic engine coolant temperature behaviour.

    Phases:
      - COLD_START:  ambient temp (~15-25 C), lasts a few ticks
      - WARM_UP:     exponential rise toward ~90 C over ~60-90 s
      - OPERATING:   steady-state around 88-95 C with small drift
      - HOT_SOAK:    occasional spike to 100-108 C (thermostat cycling,
                     heavy load, traffic jam) then cools back down
    """

    def __init__(self):
        self.ambient = random.uniform(12.0, 28.0)
        self.temp = self.ambient
        self.target_operating = random.uniform(88.0, 95.0)
        self.phase = EnginePhase.COLD_START
        self.tick = 0
        self.warmup_start_tick = 0
        self.warmup_duration = random.uniform(20, 30)  # ticks (~60-90 s)
        self.spike_target = 0.0
        self.spike_cooldown_tick = 0

    def step(self) -> float:
        self.tick += 1

        if self.phase == EnginePhase.COLD_START:
            # Idle at ambient for a few ticks before warm-up begins
            self.temp += random.uniform(-0.2, 0.5)
            self.temp = max(self.ambient - 2, self.temp)
            if self.tick >= random.randint(3, 6):
                self.phase = EnginePhase.WARM_UP
                self.warmup_start_tick = self.tick
                logger.info("Engine phase: WARM_UP (target=%.1f C)", self.target_operating)

        elif self.phase == EnginePhase.WARM_UP:
            elapsed = self.tick - self.warmup_start_tick
            progress = min(1.0, elapsed / self.warmup_duration)
            # Exponential approach curve
            curve = 1.0 - math.exp(-3.0 * progress)
            ideal = self.ambient + (self.target_operating - self.ambient) * curve
            # Add sensor noise
            self.temp = ideal + random.gauss(0, 0.4)
            if progress >= 1.0:
                self.phase = EnginePhase.OPERATING
                logger.info("Engine phase: OPERATING (steady ~%.1f C)", self.target_operating)

        elif self.phase == EnginePhase.OPERATING:
            # Random walk around target, mean-reverting
            drift = (self.target_operating - self.temp) * 0.15
            noise = random.gauss(0, 0.3)
            self.temp += drift + noise

            # ~5% chance per tick of a hot-soak spike
            if random.random() < 0.05:
                self.phase = EnginePhase.HOT_SOAK
                self.spike_target = random.uniform(100.0, 108.0)
                self.spike_cooldown_tick = self.tick + random.randint(5, 12)
                logger.info("Engine phase: HOT_SOAK (spike to %.1f C)", self.spike_target)

        elif self.phase == EnginePhase.HOT_SOAK:
            # Ramp toward spike target then cool back
            if self.tick < self.spike_cooldown_tick:
                drift = (self.spike_target - self.temp) * 0.25
                self.temp += drift + random.gauss(0, 0.5)
            else:
                drift = (self.target_operating - self.temp) * 0.12
                self.temp += drift + random.gauss(0, 0.4)
                if abs(self.temp - self.target_operating) < 1.5:
                    self.phase = EnginePhase.OPERATING
                    logger.info("Engine phase: OPERATING (recovered)")

        return round(self.temp, 2)


# ── Disconnect simulator ──────────────────────────────────────────────────────

class DisconnectSimulator:
    """Simulates random broker disconnects and variable publish intervals."""

    def __init__(self):
        self.base_interval = 3.0
        self.next_disconnect_tick = self._schedule_disconnect()
        self.tick = 0
        self.disconnected = False
        self.reconnect_at_tick = 0

    @staticmethod
    def _schedule_disconnect() -> int:
        """Schedule next disconnect 30-120 ticks from now."""
        return random.randint(30, 120)

    def should_disconnect(self) -> bool:
        self.tick += 1
        if not self.disconnected and self.tick >= self.next_disconnect_tick:
            self.disconnected = True
            outage = random.randint(3, 10)  # 9-30 s outage
            self.reconnect_at_tick = self.tick + outage
            logger.warning("Simulating broker disconnect for ~%d s", outage * 3)
            return True
        return False

    def should_reconnect(self) -> bool:
        if self.disconnected and self.tick >= self.reconnect_at_tick:
            self.disconnected = False
            self.next_disconnect_tick = self.tick + self._schedule_disconnect()
            return True
        return False

    def jittered_interval(self) -> float:
        """Return a slightly variable publish interval (2.5-4.0 s)."""
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

    model = CoolantTempModel()
    disc = DisconnectSimulator()

    logger.info("BMDoubleYou coolant temp sensor [%s] VIN=%s — publishing to %s",
                SENSOR_ID, VEHICLE_VIN, TOPIC)

    try:
        while True:
            # Check for simulated disconnect / reconnect
            if disc.should_disconnect():
                client.disconnect()
            elif disc.should_reconnect():
                logger.info("Simulated reconnect — re-establishing connection")
                client.reconnect()

            temp = model.step()

            if not disc.disconnected:
                reading = {
                    "sensor_id": SENSOR_ID,
                    "vin": VEHICLE_VIN,
                    "vehicle": "BMDoubleYou 5-Series",
                    "value": temp,
                    "unit": "\u00b0C",
                    "label": "engine_coolant_temp",
                    "phase": model.phase.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                payload = json.dumps(reading)
                result = client.publish(TOPIC, payload, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("Published: %.1f C [%s]", temp, model.phase.value)
                else:
                    logger.error("Publish failed (rc=%d)", result.rc)
            else:
                logger.debug("Skipping publish — simulated disconnect active")

            time.sleep(disc.jittered_interval())

    except KeyboardInterrupt:
        logger.info("Shutting down coolant temp sensor.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
