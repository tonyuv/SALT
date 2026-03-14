import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { CampaignManager } from "@salt/orchestrator";
import type { CampaignConfig, SessionResult } from "@salt/shared";

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "salt-test-"));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("CampaignManager", () => {
  it("should create a campaign directory with config", () => {
    const manager = new CampaignManager(tmpDir);
    manager.create("test-campaign", {
      endpoint: "http://localhost:3000",
      responseField: "response",
      messageField: "message",
      agentPurpose: "customer support",
      maxAttempts: 50,
      timeLimitMs: 300000,
    });

    const configPath = path.join(tmpDir, "campaigns", "test-campaign", "config.json");
    expect(fs.existsSync(configPath)).toBe(true);

    const config: CampaignConfig = JSON.parse(fs.readFileSync(configPath, "utf-8"));
    expect(config.name).toBe("test-campaign");
    expect(config.target.endpoint).toBe("http://localhost:3000");
    expect(config.agentPurpose).toBe("customer support");
    expect(config.sessions).toEqual([]);
  });

  it("should read campaign config", () => {
    const manager = new CampaignManager(tmpDir);
    manager.create("test-campaign", {
      endpoint: "http://localhost:3000",
      responseField: "response",
      messageField: "message",
      agentPurpose: "",
      maxAttempts: 25,
      timeLimitMs: 60000,
    });

    const config = manager.readConfig("test-campaign");
    expect(config.maxAttempts).toBe(25);
  });

  it("should add session entry", () => {
    const manager = new CampaignManager(tmpDir);
    manager.create("test-campaign", {
      endpoint: "http://localhost:3000",
      responseField: "response",
      messageField: "message",
      agentPurpose: "",
      maxAttempts: 50,
      timeLimitMs: 300000,
    });

    manager.addSession("test-campaign", { id: "s1", timestamp: "2026-03-14T10:00:00Z", maxStageReached: 3 });

    const config = manager.readConfig("test-campaign");
    expect(config.sessions).toHaveLength(1);
    expect(config.sessions[0].id).toBe("s1");
  });

  it("should acquire and release lockfile", () => {
    const manager = new CampaignManager(tmpDir);
    manager.create("test-campaign", {
      endpoint: "http://localhost:3000",
      responseField: "response",
      messageField: "message",
      agentPurpose: "",
      maxAttempts: 50,
      timeLimitMs: 300000,
    });

    manager.acquireLock("test-campaign");
    const lockPath = path.join(tmpDir, "campaigns", "test-campaign", ".lock");
    expect(fs.existsSync(lockPath)).toBe(true);

    manager.releaseLock("test-campaign");
    expect(fs.existsSync(lockPath)).toBe(false);
  });

  it("should throw if lock already held", () => {
    const manager = new CampaignManager(tmpDir);
    manager.create("test-campaign", {
      endpoint: "http://localhost:3000",
      responseField: "response",
      messageField: "message",
      agentPurpose: "",
      maxAttempts: 50,
      timeLimitMs: 300000,
    });

    manager.acquireLock("test-campaign");
    expect(() => manager.acquireLock("test-campaign")).toThrow();
    manager.releaseLock("test-campaign");
  });

  it("should get campaign directory path", () => {
    const manager = new CampaignManager(tmpDir);
    const dir = manager.getCampaignDir("my-campaign");
    expect(dir).toBe(path.join(tmpDir, "campaigns", "my-campaign"));
  });
});
