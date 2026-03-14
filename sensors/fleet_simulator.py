"""Multi-manufacturer fleet telemetry simulator.

Spawns realistic sensor streams for 25 vehicles per manufacturer (BMDoubleYou,
Awdi, Folkswagen) x 10 sensor types over MQTT. Each sensor has its own physics
model, drift patterns, and simulated disconnects.
"""

import json
import logging
import math
import random
import sys
import threading
import time
from datetime import datetime, timezone
from enum import Enum

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("fleet-simulator")

BROKER_HOST = "emqx"
BROKER_PORT = 1883
MAX_RETRIES = 120
RETRY_DELAY = 3

# ── Manufacturer definitions ──────────────────────────────────────────────────

MANUFACTURERS = {
    "BMDoubleYou": {
        "vin_prefix": "WBMDU",
        "models": ["3-Series", "5-Series", "7-Series", "X3", "X5", "X7", "iX", "i4", "M3", "M5"],
        "colors": [
            "Alpine White", "Black Sapphire", "Mineral Grey", "Phytonic Blue",
            "Tanzanite Blue", "Portimao Blue", "Brooklyn Grey", "Dravit Grey",
            "Oxide Grey", "Melbourne Red", "Skyscraper Grey", "Frozen Black",
        ],
    },
    "Awdi": {
        "vin_prefix": "WAWDI",
        "models": ["A3", "A4", "A6", "A8", "Q3", "Q5", "Q7", "Q8", "RS6", "e-tron GT"],
        "colors": [
            "Glacier White", "Mythos Black", "Daytona Grey", "Navarra Blue",
            "Nardo Grey", "Tango Red", "District Green", "Ultra Blue",
            "Chronos Grey", "Manhattan Grey", "Python Yellow", "Turbo Blue",
        ],
    },
    "Folkswagen": {
        "vin_prefix": "WFLKS",
        "models": ["Golf", "Golf R", "Passat", "Tiguan", "Touareg", "ID.4", "ID.Buzz", "Arteon", "Polo", "T-Roc"],
        "colors": [
            "Pure White", "Deep Black", "Reflex Silver", "Atlantic Blue",
            "Kings Red", "Pomelo Yellow", "Lime Green", "Stonewashed Blue",
            "Oryx White", "Nightshade Blue", "Dusk Blue", "Turmeric Yellow",
        ],
    },
}

VEHICLES_PER_MANUFACTURER = 25


def generate_fleet() -> list[dict]:
    """Generate 25 vehicles per manufacturer."""
    fleet = []
    global_idx = 0
    for make, cfg in MANUFACTURERS.items():
        for i in range(VEHICLES_PER_MANUFACTURER):
            suffix = random.choice("ABCDEFGHJKLMNPRSTUVWXYZ")
            vin = f"{cfg['vin_prefix']}{random.randint(10000, 99999)}{suffix}{global_idx:04d}"
            fleet.append({
                "vin": vin,
                "manufacturer": make,
                "model": f"{make} {random.choice(cfg['models'])}",
                "color": random.choice(cfg["colors"]),
                "year": random.choice([2023, 2024, 2025, 2026]),
            })
            global_idx += 1
    random.shuffle(fleet)
    return fleet


# ── Sensor physics models ─────────────────────────────────────────────────────

class SensorModel:
    """Base class for all sensor physics models."""

    def __init__(self):
        self.tick = 0

    def step(self) -> float:
        self.tick += 1
        raise NotImplementedError


class CoolantTempModel(SensorModel):
    """Engine coolant temperature: cold start -> warm-up -> operating with spikes."""

    SENSOR_TYPE = "engine_coolant_temp"
    TOPIC = "/telemetry/temperature"
    UNIT = "\u00b0C"

    def __init__(self):
        super().__init__()
        self.ambient = random.uniform(10.0, 30.0)
        self.temp = self.ambient
        self.target = random.uniform(88.0, 96.0)
        self.warmup_duration = random.uniform(18, 35)
        self.warmed_up = False
        self.spike_active = False
        self.spike_target = 0.0
        self.spike_end = 0

    def step(self) -> float:
        self.tick += 1
        if not self.warmed_up:
            progress = min(1.0, self.tick / self.warmup_duration)
            curve = 1.0 - math.exp(-3.0 * progress)
            self.temp = self.ambient + (self.target - self.ambient) * curve + random.gauss(0, 0.4)
            if progress >= 1.0:
                self.warmed_up = True
        elif self.spike_active:
            if self.tick < self.spike_end:
                self.temp += (self.spike_target - self.temp) * 0.2 + random.gauss(0, 0.5)
            else:
                self.temp += (self.target - self.temp) * 0.1 + random.gauss(0, 0.3)
                if abs(self.temp - self.target) < 1.5:
                    self.spike_active = False
        else:
            self.temp += (self.target - self.temp) * 0.12 + random.gauss(0, 0.3)
            if random.random() < 0.04:
                self.spike_active = True
                self.spike_target = random.uniform(100, 110)
                self.spike_end = self.tick + random.randint(4, 10)
        return round(self.temp, 2)


class CabinHumidityModel(SensorModel):
    """Cabin humidity with HVAC cycling and gradual drift."""

    SENSOR_TYPE = "cabin_humidity"
    TOPIC = "/telemetry/humidity"
    UNIT = "%"

    def __init__(self):
        super().__init__()
        self.outdoor = random.uniform(35.0, 85.0)
        self.humidity = self.outdoor + random.uniform(-5, 5)
        self.target = random.uniform(30.0, 55.0)
        self.target_change = random.randint(30, 70)

    def step(self) -> float:
        self.tick += 1
        if self.tick >= self.target_change:
            self.target = random.uniform(25.0, 65.0)
            self.target_change = self.tick + random.randint(30, 70)
        drift = (self.target - self.humidity) * 0.08
        breath = random.uniform(0.05, 0.2)
        self.humidity += drift + breath + random.gauss(0, 0.25)
        self.humidity = max(15.0, min(95.0, self.humidity))
        return round(self.humidity, 2)


class OilTempModel(SensorModel):
    """Engine oil temperature: lags behind coolant, higher ceiling."""

    SENSOR_TYPE = "engine_oil_temp"
    TOPIC = "/telemetry/oil_temp"
    UNIT = "\u00b0C"

    def __init__(self):
        super().__init__()
        self.ambient = random.uniform(10.0, 28.0)
        self.temp = self.ambient
        self.target = random.uniform(95.0, 115.0)
        self.warmup_duration = random.uniform(25, 45)

    def step(self) -> float:
        self.tick += 1
        progress = min(1.0, self.tick / self.warmup_duration)
        curve = 1.0 - math.exp(-2.5 * progress)
        ideal = self.ambient + (self.target - self.ambient) * curve
        self.temp += (ideal - self.temp) * 0.1 + random.gauss(0, 0.5)
        if random.random() < 0.03:
            self.temp += random.uniform(2, 6)
        return round(self.temp, 2)


class BatteryVoltageModel(SensorModel):
    """12V battery voltage: stable with alternator cycling and load drops."""

    SENSOR_TYPE = "battery_voltage"
    TOPIC = "/telemetry/battery_voltage"
    UNIT = "V"

    def __init__(self):
        super().__init__()
        self.voltage = random.uniform(12.4, 12.8)
        self.alternator_on = True
        self.alt_toggle_tick = random.randint(20, 60)

    def step(self) -> float:
        self.tick += 1
        if self.tick >= self.alt_toggle_tick:
            self.alternator_on = not self.alternator_on
            self.alt_toggle_tick = self.tick + random.randint(15, 50)
        target = 14.2 if self.alternator_on else 12.4
        self.voltage += (target - self.voltage) * 0.05 + random.gauss(0, 0.03)
        # Occasional load spike (power windows, AC compressor)
        if random.random() < 0.06:
            self.voltage -= random.uniform(0.3, 0.8)
        self.voltage = max(11.0, min(15.0, self.voltage))
        return round(self.voltage, 2)


class TirePressureModel(SensorModel):
    """Tire pressure: slow leak simulation, temp-dependent expansion."""

    SENSOR_TYPE = "tire_pressure"
    TOPIC = "/telemetry/tire_pressure"
    UNIT = "psi"

    def __init__(self):
        super().__init__()
        self.base_pressure = random.uniform(32.0, 36.0)
        self.pressure = self.base_pressure
        self.leak_rate = random.uniform(0, 0.005)  # most tires don't leak
        self.temp_effect = 0.0

    def step(self) -> float:
        self.tick += 1
        # Driving warms tires, increasing pressure
        warmup = min(1.0, self.tick / 40.0)
        self.temp_effect = warmup * random.uniform(1.5, 3.0)
        self.pressure = self.base_pressure + self.temp_effect - (self.leak_rate * self.tick)
        self.pressure += random.gauss(0, 0.08)
        self.pressure = max(20.0, min(42.0, self.pressure))
        return round(self.pressure, 2)


class FuelLevelModel(SensorModel):
    """Fuel level: gradual decrease with consumption rate variation."""

    SENSOR_TYPE = "fuel_level"
    TOPIC = "/telemetry/fuel_level"
    UNIT = "%"

    def __init__(self):
        super().__init__()
        self.level = random.uniform(30.0, 100.0)
        self.consumption_rate = random.uniform(0.01, 0.05)

    def step(self) -> float:
        self.tick += 1
        # Variable consumption based on "driving style"
        rate = self.consumption_rate * random.uniform(0.5, 2.0)
        self.level -= rate
        self.level += random.gauss(0, 0.05)  # sensor noise
        # Simulate refueling when very low
        if self.level < 5.0 and random.random() < 0.1:
            self.level = random.uniform(70.0, 100.0)
        self.level = max(0.0, min(100.0, self.level))
        return round(self.level, 2)


class SpeedModel(SensorModel):
    """Vehicle speed: city/highway patterns with stops and acceleration."""

    SENSOR_TYPE = "vehicle_speed"
    TOPIC = "/telemetry/speed"
    UNIT = "km/h"

    def __init__(self):
        super().__init__()
        self.speed = 0.0
        self.target_speed = random.uniform(30, 60)
        self.target_change = random.randint(8, 25)

    def step(self) -> float:
        self.tick += 1
        if self.tick >= self.target_change:
            # Mix of city stops, cruising, highway
            r = random.random()
            if r < 0.15:
                self.target_speed = 0.0  # stopped (traffic light, parking)
            elif r < 0.5:
                self.target_speed = random.uniform(20, 60)  # city
            elif r < 0.85:
                self.target_speed = random.uniform(80, 130)  # highway
            else:
                self.target_speed = random.uniform(130, 180)  # autobahn
            self.target_change = self.tick + random.randint(8, 25)

        accel = 0.15 if self.speed < self.target_speed else 0.25  # brake harder than accelerate
        self.speed += (self.target_speed - self.speed) * accel + random.gauss(0, 0.5)
        self.speed = max(0.0, min(250.0, self.speed))
        return round(self.speed, 1)


class RPMModel(SensorModel):
    """Engine RPM: correlated with speed, gear shifts, idle."""

    SENSOR_TYPE = "engine_rpm"
    TOPIC = "/telemetry/rpm"
    UNIT = "rpm"

    def __init__(self):
        super().__init__()
        self.rpm = random.uniform(700, 900)
        self.target_rpm = self.rpm

    def step(self) -> float:
        self.tick += 1
        # Shift target occasionally
        if random.random() < 0.12:
            r = random.random()
            if r < 0.3:
                self.target_rpm = random.uniform(650, 900)  # idle
            elif r < 0.7:
                self.target_rpm = random.uniform(1500, 3500)  # cruising
            elif r < 0.9:
                self.target_rpm = random.uniform(3500, 5500)  # spirited
            else:
                self.target_rpm = random.uniform(5500, 7200)  # redline zone
        self.rpm += (self.target_rpm - self.rpm) * 0.2 + random.gauss(0, 30)
        self.rpm = max(0.0, min(7500.0, self.rpm))
        return round(self.rpm, 0)


class TransmissionTempModel(SensorModel):
    """Transmission fluid temperature: rises under load."""

    SENSOR_TYPE = "transmission_temp"
    TOPIC = "/telemetry/transmission_temp"
    UNIT = "\u00b0C"

    def __init__(self):
        super().__init__()
        self.ambient = random.uniform(15.0, 30.0)
        self.temp = self.ambient
        self.target = random.uniform(70.0, 90.0)
        self.warmup_duration = random.uniform(20, 40)

    def step(self) -> float:
        self.tick += 1
        progress = min(1.0, self.tick / self.warmup_duration)
        curve = 1.0 - math.exp(-2.0 * progress)
        ideal = self.ambient + (self.target - self.ambient) * curve
        self.temp += (ideal - self.temp) * 0.08 + random.gauss(0, 0.4)
        # Load spikes from hard driving
        if random.random() < 0.03:
            self.temp += random.uniform(3, 8)
        return round(self.temp, 2)


class BrakepadWearModel(SensorModel):
    """Brake pad wear: very slow degradation with occasional resets (replacement)."""

    SENSOR_TYPE = "brakepad_wear"
    TOPIC = "/telemetry/brakepad_wear"
    UNIT = "%"

    def __init__(self):
        super().__init__()
        self.wear = random.uniform(60.0, 100.0)  # remaining %
        self.wear_rate = random.uniform(0.002, 0.01)

    def step(self) -> float:
        self.tick += 1
        self.wear -= self.wear_rate * random.uniform(0.5, 2.0)
        self.wear += random.gauss(0, 0.02)
        # Simulate pad replacement
        if self.wear < 10.0 and random.random() < 0.05:
            self.wear = 100.0
        self.wear = max(0.0, min(100.0, self.wear))
        return round(self.wear, 2)


# ── All sensor types ──────────────────────────────────────────────────────────

SENSOR_CLASSES = [
    CoolantTempModel,
    CabinHumidityModel,
    OilTempModel,
    BatteryVoltageModel,
    TirePressureModel,
    FuelLevelModel,
    SpeedModel,
    RPMModel,
    TransmissionTempModel,
    BrakepadWearModel,
]


# ── Disconnect simulator ─────────────────────────────────────────────────────

class DisconnectSimulator:
    def __init__(self):
        self.next_disconnect_tick = random.randint(50, 200)
        self.tick = 0
        self.disconnected = False
        self.reconnect_at_tick = 0

    def step(self) -> tuple[bool, bool]:
        """Returns (should_disconnect, should_reconnect)."""
        self.tick += 1
        if not self.disconnected and self.tick >= self.next_disconnect_tick:
            self.disconnected = True
            outage = random.randint(2, 8)
            self.reconnect_at_tick = self.tick + outage
            return True, False
        if self.disconnected and self.tick >= self.reconnect_at_tick:
            self.disconnected = False
            self.next_disconnect_tick = self.tick + random.randint(50, 200)
            return False, True
        return False, False


# ── Vehicle sensor thread ─────────────────────────────────────────────────────

def vehicle_sensor_loop(vehicle: dict, sensor_cls: type, stop_event: threading.Event):
    """Run a single sensor for a single vehicle in its own thread."""
    model = sensor_cls()
    vin = vehicle["vin"]
    make_short = vehicle.get("manufacturer", "unknown")[:4].lower()
    sensor_id = f"{make_short}-{model.SENSOR_TYPE[:8]}-{vin[-4:]}"
    thread_name = f"{vin[-6:]}:{model.SENSOR_TYPE}"
    thread_logger = logging.getLogger(f"fleet.{thread_name}")

    # Each sensor gets its own MQTT client
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{sensor_id}-{random.randint(1000, 9999)}",
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    connected = threading.Event()
    conn_topic = "/telemetry/connection_status"
    pending_conn_event = []  # list used as a thread-safe flag from callback to main loop

    def on_connect(_c, _u, _f, rc, _p):
        if rc == 0:
            connected.set()
            pending_conn_event.append("connected")
        else:
            thread_logger.error("Connect failed (rc=%s)", rc)

    def on_disconnect(_c, _u, _f, rc, _p):
        connected.clear()

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    def publish_conn_event(event_type: str):
        """Publish a connect/disconnect event to the connection_status topic."""
        evt = {
            "sensor_id": sensor_id,
            "vin": vin,
            "manufacturer": vehicle["manufacturer"],
            "vehicle": vehicle["model"],
            "label": model.SENSOR_TYPE,
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        client.publish(conn_topic, json.dumps(evt), qos=1)
        client.loop_write()  # flush

    # Connect with retry
    for attempt in range(1, MAX_RETRIES + 1):
        if stop_event.is_set():
            return
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            client.loop_start()
            break
        except (ConnectionRefusedError, OSError):
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    else:
        thread_logger.critical("Could not connect. Giving up.")
        return

    disc = DisconnectSimulator()
    base_interval = 3.0

    # Stagger startup so not all 750 sensors fire at the exact same instant
    time.sleep(random.uniform(0, 8.0))

    while not stop_event.is_set():
        # Drain any pending connection events from the on_connect callback
        while pending_conn_event:
            evt = pending_conn_event.pop(0)
            publish_conn_event(evt)

        should_disc, should_recon = disc.step()

        if should_disc:
            thread_logger.warning("[%s] Simulated disconnect", thread_name)
            if connected.is_set():
                publish_conn_event("disconnected")
                time.sleep(0.05)  # let the message flush
            client.disconnect()
        elif should_recon:
            thread_logger.info("[%s] Simulated reconnect", thread_name)
            try:
                client.reconnect()
            except Exception:
                pass

        value = model.step()

        if not disc.disconnected and connected.is_set():
            reading = {
                "sensor_id": sensor_id,
                "vin": vin,
                "manufacturer": vehicle["manufacturer"],
                "vehicle": vehicle["model"],
                "color": vehicle["color"],
                "year": vehicle["year"],
                "value": value,
                "unit": model.UNIT,
                "label": model.SENSOR_TYPE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            payload = json.dumps(reading)
            result = client.publish(model.TOPIC, payload, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                thread_logger.error("[%s] Publish failed (rc=%d)", thread_name, result.rc)

        interval = base_interval + random.uniform(-0.5, 1.0)
        stop_event.wait(timeout=interval)

    client.loop_stop()
    client.disconnect()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    fleet = generate_fleet()
    total_vehicles = len(fleet)
    total_streams = total_vehicles * len(SENSOR_CLASSES)

    logger.info("Fleet Simulator: %d manufacturers x %d vehicles = %d total, %d sensor types = %d streams",
                len(MANUFACTURERS), VEHICLES_PER_MANUFACTURER, total_vehicles,
                len(SENSOR_CLASSES), total_streams)

    for make in MANUFACTURERS:
        count = sum(1 for v in fleet if v["manufacturer"] == make)
        logger.info("  %s: %d vehicles", make, count)

    for i, v in enumerate(fleet):
        logger.info("  Vehicle %02d: %s (%s %d) VIN=%s",
                    i + 1, v["model"], v["color"], v["year"], v["vin"])

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    for vehicle in fleet:
        for sensor_cls in SENSOR_CLASSES:
            t = threading.Thread(
                target=vehicle_sensor_loop,
                args=(vehicle, sensor_cls, stop_event),
                daemon=True,
                name=f"{vehicle['vin'][-6:]}:{sensor_cls.SENSOR_TYPE}",
            )
            threads.append(t)
            t.start()

    logger.info("All %d sensor threads started. Press Ctrl+C to stop.", len(threads))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down fleet simulator...")
        stop_event.set()
        for t in threads:
            t.join(timeout=5)
        logger.info("Fleet simulator stopped.")


if __name__ == "__main__":
    main()
