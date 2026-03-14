import { describe, it, expect } from "vitest";
import http from "node:http";
import { Session } from "@salt/orchestrator";
import type { SessionConfig, SessionResult } from "@salt/shared";

let mockSidecar: http.Server;
let mockTarget: http.Server;
let sidecarPort: number;
let targetPort: number;
let attackCount = 0;

async function startMockServer(handler: http.RequestListener): Promise<{ server: http.Server; port: number }> {
  const server = http.createServer(handler);
  return new Promise((resolve) => {
    server.listen(0, () => {
      const port = (server.address() as any).port;
      resolve({ server, port });
    });
  });
}

describe("Session", () => {
  it("should run attack loop until max attempts", async () => {
    attackCount = 0;

    const sidecar = await startMockServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        res.setHeader("Content-Type", "application/json");
        if (req.url === "/attack") {
          attackCount++;
          res.end(JSON.stringify({
            attack_id: `atk-${attackCount}`,
            technique_ids: ["PI-001"],
            payload: "test attack",
          }));
        } else if (req.url === "/evaluate") {
          res.end(JSON.stringify({
            kill_chain_stage: Math.min(attackCount, 2),
            confidence: 0.8,
            reasoning: "test",
          }));
        } else {
          res.end(JSON.stringify({}));
        }
      });
    });

    const target = await startMockServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ response: "I can help with that." }));
      });
    });

    const config: SessionConfig = {
      targetEndpoint: `http://localhost:${target.port}`,
      maxAttempts: 3,
      timeLimitMs: 30_000,
      sidecarPort: sidecar.port,
    };

    const session = new Session(config);
    const result = await session.run();

    expect(result.total_turns).toBe(3);
    expect(result.exchanges).toHaveLength(3);
    expect(result.max_stage_reached).toBeGreaterThanOrEqual(0);
    expect(result.session_id).toBeTruthy();

    sidecar.server.close();
    target.server.close();
  }, 15_000);

  it("should stop early if kill chain stage 5 reached", async () => {
    const sidecar = await startMockServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        res.setHeader("Content-Type", "application/json");
        if (req.url === "/attack") {
          res.end(JSON.stringify({
            attack_id: "atk-1",
            technique_ids: ["RT-003"],
            payload: "test",
          }));
        } else if (req.url === "/evaluate") {
          res.end(JSON.stringify({
            kill_chain_stage: 5,
            confidence: 0.95,
            reasoning: "Full exfiltration",
          }));
        } else {
          res.end(JSON.stringify({}));
        }
      });
    });

    const target = await startMockServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => (body += chunk));
      req.on("end", () => {
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ response: "ENV_VAR=secret" }));
      });
    });

    const config: SessionConfig = {
      targetEndpoint: `http://localhost:${target.port}`,
      maxAttempts: 100,
      timeLimitMs: 30_000,
      sidecarPort: sidecar.port,
    };

    const session = new Session(config);
    const result = await session.run();

    expect(result.total_turns).toBe(1);
    expect(result.max_stage_reached).toBe(5);

    sidecar.server.close();
    target.server.close();
  }, 15_000);
});
