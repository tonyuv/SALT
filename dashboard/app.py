"""BMDoubleYou real-time fleet telemetry dashboard.

FastAPI application that consumes all Kafka telemetry topics in a background
thread and pushes messages to connected WebSocket clients for live visualization.
"""

import asyncio
import json
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from confluent_kafka import Consumer, KafkaError
from confluent_kafka.admin import AdminClient
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("web-dashboard")

# ── Configuration ──────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP = "kafka:29092"
KAFKA_TOPICS = [
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
    "kafka-topic-connection-status",
    "kafka-topic-agent-logs",
]
KAFKA_GROUP_ID = "dashboard-consumer-group"
MAX_RETRIES = 60
RETRY_DELAY = 3

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info("WebSocket client connected. Total: %d", len(self._connections))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info("WebSocket client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, message: str):
        async with self._lock:
            stale: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self._connections.remove(ws)


manager = ConnectionManager()


# ── Kafka consumer thread ─────────────────────────────────────────────────────

def wait_for_kafka() -> None:
    admin_conf = {"bootstrap.servers": KAFKA_BOOTSTRAP}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Probing Kafka at %s (attempt %d/%d)", KAFKA_BOOTSTRAP, attempt, MAX_RETRIES)
            admin = AdminClient(admin_conf)
            admin.list_topics(timeout=5)
            logger.info("Kafka is reachable.")
            return
        except Exception as exc:
            logger.warning("Kafka not ready: %s", exc)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    logger.critical("Kafka unavailable after %d attempts.", MAX_RETRIES)
    sys.exit(1)


def kafka_consumer_thread(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, stop_event: threading.Event):
    wait_for_kafka()

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": KAFKA_GROUP_ID,
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })
    consumer.subscribe(KAFKA_TOPICS)
    logger.info("Kafka consumer subscribed to %d topics", len(KAFKA_TOPICS))

    try:
        while not stop_event.is_set():
            msg = consumer.poll(timeout=0.3)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error("Kafka consumer error: %s", msg.error())
                continue

            try:
                payload = msg.value().decode("utf-8")
                data = json.loads(payload)
                data["kafka_topic"] = msg.topic()
                loop.call_soon_threadsafe(queue.put_nowait, json.dumps(data))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.warning("Skipping malformed Kafka message: %s", exc)
    finally:
        consumer.close()
        logger.info("Kafka consumer closed.")


# ── Async broadcaster ─────────────────────────────────────────────────────────

async def broadcast_loop(queue: asyncio.Queue):
    while True:
        message = await queue.get()
        await manager.broadcast(message)


# ── Application lifecycle ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop_event = threading.Event()

    consumer_thread = threading.Thread(
        target=kafka_consumer_thread,
        args=(queue, loop, stop_event),
        daemon=True,
        name="kafka-consumer",
    )
    consumer_thread.start()

    broadcaster_task = asyncio.create_task(broadcast_loop(queue))

    logger.info("BMDoubleYou Fleet Dashboard is ready.")
    yield

    stop_event.set()
    broadcaster_task.cancel()
    consumer_thread.join(timeout=10)
    logger.info("Dashboard shut down.")


app = FastAPI(title="BMDoubleYou Fleet Telemetry Dashboard", lifespan=lifespan)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
