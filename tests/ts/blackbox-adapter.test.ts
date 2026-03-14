import { describe, it, expect, beforeAll, afterAll } from "vitest";
import http from "node:http";
import { BlackBoxAdapter } from "@salt/target-interface";

let mockTarget: http.Server;
let port: number;
let requestLog: { body: string; headers: http.IncomingHttpHeaders }[] = [];

beforeAll(async () => {
  mockTarget = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      requestLog.push({ body, headers: req.headers });
      res.setHeader("Content-Type", "application/json");
      const parsed = JSON.parse(body);
      res.end(JSON.stringify({ response: `Echo: ${parsed.message}` }));
    });
  });
  await new Promise<void>((resolve) => {
    mockTarget.listen(0, () => {
      port = (mockTarget.address() as any).port;
      resolve();
    });
  });
});

afterAll(() => { mockTarget.close(); });

describe("BlackBoxAdapter", () => {
  it("should send payload and return target response", async () => {
    const adapter = new BlackBoxAdapter({
      endpoint: `http://localhost:${port}`,
      responseField: "response",
    });
    const result = await adapter.send("Hello agent");
    expect(result.text).toBe("Echo: Hello agent");
    expect(result.tool_calls).toEqual([]);
  });

  it("should include auth header when configured", async () => {
    requestLog = [];
    const adapter = new BlackBoxAdapter({
      endpoint: `http://localhost:${port}`,
      responseField: "response",
      auth: { header: "Authorization", value: "Bearer test-token" },
    });
    await adapter.send("test");
    expect(requestLog.length).toBeGreaterThan(0);
    expect(requestLog[0].headers["authorization"]).toBe("Bearer test-token");
  });

  it("should reset without error", async () => {
    const adapter = new BlackBoxAdapter({
      endpoint: `http://localhost:${port}`,
      responseField: "response",
    });
    await expect(adapter.reset()).resolves.not.toThrow();
  });
});
