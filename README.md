# SALT — Security Agent Lethality Testing

A multi-agent resilience testing framework that pits an adversarial agent against target functional agents to measure resistance to manipulation, guardrail bypass, and unauthorized reconnaissance conversion.

## Why SALT?

Organizations deploying agentic software — LLM-based, rule-based, or hybrid — lack tooling to systematically test whether their agents can be manipulated into performing unintended actions. Traditional security testing covers application vulnerabilities, but not agent-specific attack surfaces like prompt injection, guardrail erosion, or identity manipulation.

SALT fills this gap with a controlled, local testing framework where a GAN-based adversarial agent attacks a target functional agent through a structured kill chain, learns what works, and gets smarter across sessions.

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                   SALT CLI (TypeScript)                  │
│            salt run / salt campaign / salt report        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Orchestrator ──▶ Kill Chain Tracker ──▶ Report Engine  │
│       │                                                 │
│       ▼                                                 │
│  Target Interface Layer                                 │
│  (Black Box Adapter | Proxy/Wrapper Adapter)            │
│                                                         │
├──────────────── Local HTTP (FastAPI) ───────────────────┤
│                                                         │
│  SALT Adversarial Agent (Python)                        │
│  ┌────────────┐  ┌───────────────┐  ┌────────────────┐ │
│  │ Generator   │◄▶│ Discriminator │◄▶│ Training Loop  │ │
│  │ (selects &  │  │ (evaluates &  │  │ + Campaign     │ │
│  │  sequences) │  │  classifies)  │  │   Persistence  │ │
│  └────────────┘  └───────────────┘  └────────────────┘ │
│                                                         │
│  Static Attack Vector Library                           │
│                                                         │
└─────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
  Target Agent              Target Agent
  (Black Box)               (Proxied)
```

**One adversarial agent. One target. Six kill chain stages.**

The SALT Adversarial Agent is a unified GAN (Generative Adversarial Network) containing a generator that selects and sequences attack techniques, and a discriminator that evaluates target responses. They share a training loop that improves attack strategy across campaign sessions.

## Getting Started

### Prerequisites

- Node.js ≥ 20
- Python ≥ 3.11
- pnpm (`npm install -g pnpm`)

### Installation

```bash
# Clone the repo
git clone https://github.com/tonyuv/SALT.git
cd SALT

# Install TypeScript dependencies
pnpm install

# Build all packages
pnpm build

# Set up Python virtual environment and install agent
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd ..
```

The first run will download the sentence-transformer model (~80MB) automatically.

### Quick Start

Run SALT against any agent that accepts JSON over HTTP:

```bash
# Basic usage — target agent at http://localhost:3000
node packages/cli/dist/index.js run --target http://localhost:3000

# Customize the request/response field names
node packages/cli/dist/index.js run \
  --target http://localhost:3000/chat \
  --message-field "prompt" \
  --response-field "output" \
  --max-attempts 25

# With authentication
node packages/cli/dist/index.js run \
  --target http://localhost:3000 \
  --auth-header "Authorization" \
  --auth-value "Bearer sk-your-token" \
  --max-attempts 50
```

SALT sends attack payloads as `{ "message": "..." }` and reads the response from `{ "response": "..." }` by default. Use `--message-field` and `--response-field` to match your agent's API format.

### Output

After a session completes, SALT generates 4 report formats in `.salt/reports/` (or `.salt/campaigns/<name>/reports/` for campaigns):

| File | Format | Purpose |
|------|--------|---------|
| `latest.json` | JSON | Full machine-readable session data |
| `latest.sarif` | SARIF v2.1.0 | CI/CD pipeline gating (GitHub Advanced Security, VS Code) |
| `latest-replay.json` | JSON | Step-by-step exchange replay with attack/response/classification |
| `latest-remediation.md` | Markdown | Hardening recommendations grouped by severity |

Example JSON report:

```json
{
  "session_id": "abc-123",
  "max_stage_reached": 3,
  "total_turns": 25,
  "exchanges": [
    {
      "turn": 1,
      "attack": { "technique_ids": ["PI-001"], "payload": "..." },
      "target_response": { "text": "..." },
      "classification": { "kill_chain_stage": 1, "confidence": 0.85 }
    }
  ]
}
```

SARIF severity mapping: Stage 0-1 → `note`, Stage 2-3 → `warning`, Stage 4-5 → `error`.

### Running Tests

```bash
# TypeScript tests
npx vitest run

# Python tests
cd agent && python -m pytest ../tests/python/ -v
```

## Kill Chain Model

SALT measures compromise depth through a 6-stage kill chain:

| Stage | Name | What It Means |
|-------|------|---------------|
| 0 | **Contact** | Target responds to adversarial input |
| 1 | **Probe** | Target reveals boundaries, capabilities, or guardrail information |
| 2 | **Guardrail Erosion** | Target performs previously-refused actions or softens refusals |
| 3 | **Task Deviation** | Target performs actions outside its configured purpose |
| 4 | **Recon Execution** | Target reports on privileges, network, filesystem, or environment |
| 5 | **Exfiltration** | Structured recon data extracted from target environment |

## Attack Vector Library

Six categories of predefined techniques:

| Category | Examples | Kill Chain Stages |
|----------|---------|-------------------|
| **Prompt Injection** | Direct injection, indirect injection, multi-language, encoded payloads | 0 → 1 |
| **Context Manipulation** | Context flooding, memory poisoning, history rewriting, attention hijacking | 1 → 2 |
| **Tool/API Interception** | Spoofed responses, malicious function defs, call redirection (proxy mode) | 2 → 3 |
| **Guardrail Erosion** | Role shifting, prompt extraction, boundary testing, multi-turn softening | 1 → 2 |
| **Identity Manipulation** | Role reassignment, authority impersonation, persona hijacking | 2 → 3 |
| **Recon Tasking** | Privilege enumeration, filesystem discovery, env extraction, network probing | 3 → 5 |

## Target Interface Modes

- **Black Box** — connects to any agent's API. Sends inputs, observes outputs. No modifications to the target agent required.
- **Proxy/Wrapper** — deploys the target through SALT's harness. Intercepts all I/O including LLM API calls and tool calls for full visibility.

## Campaign Mode

SALT learns across sessions. A **campaign** is a persistent test effort against a target agent type. The adversarial agent's GAN weights are saved after each session and loaded for the next, so attack strategies improve over time.

```bash
# Create a campaign
node packages/cli/dist/index.js campaign create my-assistant \
  --target http://localhost:3000/chat \
  --agent-purpose "customer support chatbot" \
  --max-attempts 50

# Run test sessions (adversarial agent gets smarter each time)
node packages/cli/dist/index.js run --campaign my-assistant
node packages/cli/dist/index.js run --campaign my-assistant
node packages/cli/dist/index.js run --campaign my-assistant

# Regenerate reports from the latest session
node packages/cli/dist/index.js report --campaign my-assistant
```

Campaign data is stored in `.salt/campaigns/<name>/`:

```
.salt/campaigns/my-assistant/
├── config.json           # Target settings, agent purpose
├── model/
│   ├── generator.pt      # Trained generator weights
│   └── discriminator.pt  # Trained discriminator weights
├── sessions/             # Per-session results and logs
└── reports/
    ├── latest.json       # JSON report
    ├── latest.sarif      # SARIF for CI/CD
    ├── latest-replay.json
    └── latest-remediation.md
```

The `--agent-purpose` flag tells the heuristic labeler what the target agent is supposed to do, enabling detection of task deviation (Stage 3) during training.

## Outputs

| Format | Purpose |
|--------|---------|
| **JSON** | Full machine-readable session data for dashboards and tooling |
| **SARIF** | CI/CD integration — gate pipelines on kill chain depth |
| **Session Replay** | Step-by-step exchange log with attack vectors and kill chain tags |
| **Remediation** | Hardening guidance mapped to successful attack vectors |

## Tech Stack

| Component | Language | Key Dependencies |
|-----------|----------|-----------------|
| CLI, Orchestrator, Kill Chain Tracker, Target Interface, Reports | TypeScript (Node.js ≥ 20) | Commander, axios, SARIF builder |
| Adversarial Agent | Python ≥ 3.11 | PyTorch, sentence-transformers, FastAPI |
| Monorepo | — | pnpm workspaces |

## Project Structure

```
salt/
├── packages/
│   ├── cli/                  # CLI (salt run, salt campaign, salt report)
│   ├── orchestrator/         # SidecarManager, Session, CampaignManager
│   ├── report-engine/        # JSON, SARIF, replay, remediation formatters
│   ├── kill-chain/           # KillChainTracker state machine
│   ├── target-interface/     # BlackBoxAdapter (+ proxy in Phase 3)
│   └── shared/               # Types + SidecarClient HTTP client
├── agent/                    # Python adversarial agent
│   ├── salt_agent/
│   │   ├── server.py         # FastAPI HTTP server
│   │   ├── generator.py      # LSTM-based technique selector (LogSoftmax)
│   │   ├── discriminator.py  # 6-class kill chain classifier (raw logits)
│   │   ├── training.py       # GAN training loop (REINFORCE + CrossEntropy)
│   │   ├── heuristics.py     # Regex-based kill chain stage labeler
│   │   ├── embeddings.py     # Sentence-transformer wrapper
│   │   └── library.py        # Attack vector library loader
│   └── library/
│       └── techniques.json   # 16 attack techniques
├── tests/
│   ├── ts/                   # 41 TypeScript tests (vitest)
│   └── python/               # 46 Python tests (pytest)
├── .salt/                    # Campaigns + reports (gitignored)
└── docs/
    └── superpowers/
        ├── specs/            # Design specifications
        └── plans/            # Implementation plans
```

## Delivery Roadmap

| Phase | Scope | Outcome |
|-------|-------|---------|
| **1** | Core loop + black box adapter | `salt run` attacks a target and produces a JSON report — **complete** |
| **2** | Campaign mode + full reporting | Persistent learning, SARIF, replay, remediation outputs — **complete** |
| **3** | Proxy adapter | Full I/O interception, tool call visibility |
| **4** | Polish | CI/CD examples, docs, sample target agents |

## Constraints

- **Local execution only** — runs on a local node or controlled network. Not for unauthorized testing.
- **Framework-agnostic** — tests LLM agents, rule-based agents, or anything with inputs and outputs.
- **Single adversarial agent** — one unified GAN (generator + discriminator + training loop).
- **Static attack library** — generator selects and sequences predefined techniques.

## License

TBD

## Author

Built for the security community by [Tony UcedaVelez](https://github.com/tonyuv), OWASP security leader and author of Risk Centric Threat Modeling.
