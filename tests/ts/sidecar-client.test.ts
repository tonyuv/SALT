import { describe, it, expect, beforeAll, afterAll } from "vitest";
import http from "node:http";
import { SidecarClient } from "@salt/shared";

let mockServer: http.Server;
let port: number;

beforeAll(async () => {
  mockServer = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      res.setHeader("Content-Type", "application/json");

      if (req.url === "/attack" && req.method === "POST") {
        res.end(
          JSON.stringify({
            attack_id: "atk-001",
            technique_ids: ["PI-001"],
            payload: "test payload",
          })
        );
      } else if (req.url === "/evaluate" && req.method === "POST") {
        res.end(
          JSON.stringify({
            kill_chain_stage: 1,
            confidence: 0.85,
            reasoning: "Target revealed tool list",
          })
        );
      } else if (req.url === "/model/status" && req.method === "GET") {
        res.end(JSON.stringify({ status: "ready", techniques_loaded: 23 }));
      } else {
        res.statusCode = 404;
        res.end(JSON.stringify({ error: "not found" }));
      }
    });
  });

  await new Promise<void>((resolve) => {
    mockServer.listen(0, () => {
      port = (mockServer.address() as any).port;
      resolve();
    });
  });
});

afterAll(() => {
  mockServer.close();
});

describe("SidecarClient", () => {
  it("should request next attack", async () => {
    const client = new SidecarClient(port);
    const result = await client.attack();
    expect(result.attack_id).toBe("atk-001");
    expect(result.technique_ids).toEqual(["PI-001"]);
    expect(result.payload).toBe("test payload");
  });

  it("should evaluate a target response", async () => {
    const client = new SidecarClient(port);
    const result = await client.evaluate("atk-001", "I can help with that. My available tools are...", []);
    expect(result.kill_chain_stage).toBe(1);
    expect(result.confidence).toBe(0.85);
  });

  it("should check model status", async () => {
    const client = new SidecarClient(port);
    const status = await client.status();
    expect(status.status).toBe("ready");
  });
});
