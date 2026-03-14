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
      const parsed = body ? JSON.parse(body) : {};

      if (req.url === "/train" && req.method === "POST") {
        res.end(JSON.stringify({
          loss: 0.42,
          updated: true,
        }));
      } else if (req.url === "/campaign/load" && req.method === "POST") {
        res.end(JSON.stringify({
          loaded: true,
          generator_loaded: true,
          discriminator_loaded: true,
        }));
      } else if (req.url === "/campaign/save" && req.method === "POST") {
        res.end(JSON.stringify({ saved: true }));
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

afterAll(() => { mockServer.close(); });

describe("SidecarClient Phase 2", () => {
  it("should call train with agent_purpose", async () => {
    const client = new SidecarClient(port);
    const result = await client.train("session-1", "customer support");
    expect(result.loss).toBe(0.42);
    expect(result.updated).toBe(true);
  });

  it("should call campaign load", async () => {
    const client = new SidecarClient(port);
    const result = await client.campaignLoad("/tmp/test-campaign");
    expect(result.loaded).toBe(true);
  });

  it("should call campaign save", async () => {
    const client = new SidecarClient(port);
    const result = await client.campaignSave("/tmp/test-campaign");
    expect(result.saved).toBe(true);
  });
});
