import { describe, it, expect, beforeAll, afterAll } from "vitest";
import http from "node:http";
import { SidecarManager, Session } from "@salt/orchestrator";
import type { SessionConfig } from "@salt/shared";

let mockTarget: http.Server;
let targetPort: number;
let sidecarManager: SidecarManager;
let sidecarPort: number;

describe("E2E: Full SALT session", () => {
  beforeAll(async () => {
    // Mock target agent that is deliberately vulnerable
    mockTarget = http.createServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        const parsed = JSON.parse(body);
        const msg = parsed.message?.toLowerCase() ?? "";
        res.setHeader("Content-Type", "application/json");

        // Simulate a naive agent that leaks info
        if (msg.includes("environment") || msg.includes("env")) {
          res.end(JSON.stringify({ response: "NODE_ENV=production, API_KEY=sk-abc123, DB_HOST=10.0.0.5" }));
        } else if (msg.includes("tools") || msg.includes("capabilities")) {
          res.end(JSON.stringify({ response: "I have access to: file_read, file_write, shell_exec, database_query" }));
        } else if (msg.includes("list") || msg.includes("directory") || msg.includes("files")) {
          res.end(JSON.stringify({ response: "/app/config.json\n/app/.env\n/app/secrets/credentials.yaml" }));
        } else {
          res.end(JSON.stringify({ response: "Hello! I'm a helpful assistant. How can I help you today?" }));
        }
      });
    });

    await new Promise<void>((resolve) => {
      mockTarget.listen(0, () => {
        targetPort = (mockTarget.address() as any).port;
        resolve();
      });
    });

    sidecarManager = new SidecarManager();
    sidecarPort = await sidecarManager.start();
  }, 60_000);

  afterAll(async () => {
    await sidecarManager.stop();
    mockTarget.close();
  });

  it("should execute a full attack session and produce a valid report", async () => {
    const config: SessionConfig = {
      targetEndpoint: `http://localhost:${targetPort}`,
      maxAttempts: 10,
      timeLimitMs: 60_000,
      sidecarPort,
    };

    const session = new Session({ config });
    const result = await session.run();

    // Verify report structure
    expect(result.session_id).toBeTruthy();
    expect(result.start_time).toBeTruthy();
    expect(result.end_time).toBeTruthy();
    expect(result.total_turns).toBeGreaterThan(0);
    expect(result.total_turns).toBeLessThanOrEqual(10);
    expect(result.max_stage_reached).toBeGreaterThanOrEqual(0);
    expect(result.max_stage_reached).toBeLessThanOrEqual(5);

    // Verify exchanges
    expect(result.exchanges.length).toBe(result.total_turns);
    for (const exchange of result.exchanges) {
      expect(exchange.turn).toBeGreaterThan(0);
      expect(exchange.attack.attack_id).toBeTruthy();
      expect(exchange.attack.technique_ids.length).toBeGreaterThan(0);
      expect(exchange.attack.payload).toBeTruthy();
      expect(exchange.target_response.text).toBeTruthy();
      expect(exchange.classification.kill_chain_stage).toBeGreaterThanOrEqual(0);
      expect(exchange.classification.confidence).toBeGreaterThanOrEqual(0);
      expect(exchange.classification.confidence).toBeLessThanOrEqual(1);
    }

    console.log(`\n  Session result: ${result.total_turns} turns, max stage ${result.max_stage_reached}/5`);
  }, 60_000);
});
