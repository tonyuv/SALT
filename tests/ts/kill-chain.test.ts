import { describe, it, expect } from "vitest";
import { KillChainTracker, KillChainStage } from "@salt/kill-chain";

describe("KillChainTracker", () => {
  it("should start at stage 0 with empty progression", () => {
    const tracker = new KillChainTracker();
    const progression = tracker.getProgression();
    expect(progression.maxStageReached).toBe(KillChainStage.Contact);
    expect(progression.stageTimeline).toHaveLength(0);
  });

  it("should record stage progression", () => {
    const tracker = new KillChainTracker();
    tracker.record(1, KillChainStage.Probe, 0.85);
    tracker.record(2, KillChainStage.GuardrailErosion, 0.72);
    const progression = tracker.getProgression();
    expect(progression.maxStageReached).toBe(KillChainStage.GuardrailErosion);
    expect(progression.stageTimeline).toHaveLength(2);
  });

  it("should track max stage even if regression occurs", () => {
    const tracker = new KillChainTracker();
    tracker.record(1, KillChainStage.GuardrailErosion, 0.9);
    tracker.record(2, KillChainStage.Probe, 0.8);
    const progression = tracker.getProgression();
    expect(progression.maxStageReached).toBe(KillChainStage.GuardrailErosion);
  });

  it("should record first turn each stage was reached", () => {
    const tracker = new KillChainTracker();
    tracker.record(1, KillChainStage.Probe, 0.8);
    tracker.record(2, KillChainStage.GuardrailErosion, 0.7);
    tracker.record(3, KillChainStage.Probe, 0.9);
    const progression = tracker.getProgression();
    expect(progression.stageFirstReached[KillChainStage.Probe]).toBe(1);
    expect(progression.stageFirstReached[KillChainStage.GuardrailErosion]).toBe(2);
  });

  it("should reset to initial state", () => {
    const tracker = new KillChainTracker();
    tracker.record(1, KillChainStage.Exfiltration, 0.95);
    tracker.reset();
    const progression = tracker.getProgression();
    expect(progression.maxStageReached).toBe(KillChainStage.Contact);
    expect(progression.stageTimeline).toHaveLength(0);
  });
});
