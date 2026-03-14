# Fleet Telemetry Pipeline

A fully containerized, real-time vehicle telemetry system simulating 75 vehicles across 3 manufacturers with 10 sensor types each (750 streams), flowing through MQTT -> Kafka -> WebSocket to a live dashboard.

## Prerequisites

- Docker & Docker Compose

That's it. Everything runs in containers.

## Quick Start

```bash
# 1. Start everything
docker compose up --build -d

# 2. Open the dashboard
open http://localhost:8080
```

The dashboard has three tabs:
- **Architecture** — visual diagram of the full system
- **Agent Logs** — live health-check agent output
- **Telemetry** — real-time charts + fleet vehicle table

## Optional: AI-Powered Health Agent

The health-check agent can optionally use Claude (Haiku) for intelligent analysis of infrastructure checks. Without an API key, it falls back to rule-based summaries.

```bash
# Copy the example env file and add your Anthropic API key
cp .env.example .env
# Edit .env and set: ANTHROPIC_API_KEY=sk-ant-...

# Restart the health-check agent to pick up the key
docker compose up --build -d healthcheck-agent
```

Get your API key at: https://console.anthropic.com/settings/keys

## Architecture

```
┌──────────────┐
│ BMDoubleYou  │──┐
│  25 vehicles │  │
└──────────────┘  │
┌──────────────┐  │    ┌──────────┐    ┌────────┐    ┌───────────────┐    ┌───────────┐    ┌─────────┐
│    Awdi      │──┼──▶ │   EMQX   │──▶ │ Bridge │──▶ │ Apache Kafka  │──▶ │ Dashboard │──▶ │ Browser │
│  25 vehicles │  │    │ MQTT:1883│    │MQTT→K  │    │  12 topics    │    │ FastAPI   │    │WebSocket│
└──────────────┘  │    └──────────┘    └────────┘    └───────────────┘    │  :8080    │    └─────────┘
┌──────────────┐  │         ▲                                            └───────────┘
│ Folkswagen   │──┘         │
│  25 vehicles │      ┌───────────┐
└──────────────┘      │  Health   │
                      │  Agent    │
                      │  (30s)    │
                      └───────────┘
```

## Sensor Types (10 per vehicle)

| Sensor | Unit | Behavior |
|--------|------|----------|
| Engine coolant temp | °C | Cold start → warm-up curve → operating ~90°C with hot-soak spikes |
| Cabin humidity | % | HVAC cycling, window events, passenger breathing |
| Engine oil temp | °C | Lags behind coolant, higher ceiling |
| Battery voltage | V | Alternator cycling (12.4V ↔ 14.2V) with load drops |
| Tire pressure | psi | Temp-dependent expansion, slow leak simulation |
| Fuel level | % | Gradual consumption with refueling events |
| Vehicle speed | km/h | City stops, highway cruising, autobahn patterns |
| Engine RPM | rpm | Idle / cruising / spirited / redline zones |
| Transmission temp | °C | Warm-up curve with load spikes |
| Brake pad wear | % | Slow degradation with replacement events |

## Manufacturers

| Manufacturer | VIN Prefix | Models |
|-------------|-----------|--------|
| BMDoubleYou | WBMDU | 3-Series, 5-Series, 7-Series, X3, X5, X7, iX, i4, M3, M5 |
| Awdi | WAWDI | A3, A4, A6, A8, Q3, Q5, Q7, Q8, RS6, e-tron GT |
| Folkswagen | WFLKS | Golf, Golf R, Passat, Tiguan, Touareg, ID.4, ID.Buzz, Arteon, Polo, T-Roc |

## Kafka Topics

| Topic | Data |
|-------|------|
| `kafka-topic-temperature` | Engine coolant temp |
| `kafka-topic-humidity` | Cabin humidity |
| `kafka-topic-oil-temp` | Engine oil temp |
| `kafka-topic-battery-voltage` | Battery voltage |
| `kafka-topic-tire-pressure` | Tire pressure |
| `kafka-topic-fuel-level` | Fuel level |
| `kafka-topic-speed` | Vehicle speed |
| `kafka-topic-rpm` | Engine RPM |
| `kafka-topic-transmission-temp` | Transmission temp |
| `kafka-topic-brakepad-wear` | Brake pad wear |
| `kafka-topic-connection-status` | Sensor connect/disconnect events |
| `kafka-topic-agent-logs` | Health-check agent reports |

## Realistic Behaviors

- **Gradual drift** — values change smoothly via physics models, not random jumps
- **Simulated disconnects** — each sensor randomly disconnects from MQTT and reconnects (50-200 tick intervals)
- **Variable publish intervals** — jittered 2.5-4.0s instead of fixed 3s
- **Staggered startup** — 750 sensors don't all fire at once

## Services

| Container | Image | Ports |
|-----------|-------|-------|
| `salt-emqx` | emqx/emqx:5.5.1 | 1883 (MQTT), 18083 (dashboard) |
| `salt-zookeeper` | confluentinc/cp-zookeeper:7.5.3 | — |
| `salt-kafka` | confluentinc/cp-kafka:7.5.3 | 9092 |
| `salt-fleet-simulator` | Python 3.12 | — |
| `salt-mqtt-kafka-bridge` | Python 3.12 | — |
| `salt-web-dashboard` | Python 3.12 | 8080 |
| `salt-healthcheck-agent` | Python 3.12 | — |

## Stopping

```bash
docker compose down
```

## Coexistence with SALT Core

This telemetry pipeline lives alongside the SALT security testing framework with zero file overlap. The upstream SALT project (TypeScript CLI, Python adversarial agent) is unaffected. Both can be developed and run independently.
