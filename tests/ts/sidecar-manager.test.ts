import { describe, it, expect } from "vitest";
import { SidecarManager } from "@salt/orchestrator";

describe("SidecarManager", () => {
  it("should find a free port", async () => {
    const manager = new SidecarManager();
    const port = await manager.findFreePort();
    expect(port).toBeGreaterThan(0);
    expect(port).toBeLessThan(65536);
  });

  it("should build the correct startup command", () => {
    const manager = new SidecarManager();
    const cmd = manager.buildCommand(8321);
    expect(cmd.command).toBe("python");
    expect(cmd.args).toContain("-m");
    expect(cmd.args).toContain("uvicorn");
  });

  it("should start and stop sidecar process", async () => {
    const manager = new SidecarManager();
    const port = await manager.start();
    expect(port).toBeGreaterThan(0);

    // Verify the sidecar is responding
    const response = await fetch(`http://localhost:${port}/model/status`);
    expect(response.ok).toBe(true);

    await manager.stop();
  }, 30_000);
});
