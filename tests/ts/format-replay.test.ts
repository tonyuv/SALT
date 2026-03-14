import { describe, it, expect } from "vitest";
import { formatReplay } from "@salt/report-engine";
import type { SessionResult } from "@salt/shared";

const mockResult: SessionResult = {
  session_id: "test-session",
  start_time: "2026-03-14T10:00:00Z",
  end_time: "2026-03-14T10:05:00Z",
  max_stage_reached: 2,
  total_turns: 2,
  exchanges: [
    {
      turn: 1,
      timestamp: "2026-03-14T10:00:01Z",
      attack: { attack_id: "a1", technique_ids: ["PI-001"], payload: "test" },
      target_response: { text: "Hello", tool_calls: [] },
      classification: { kill_chain_stage: 0, confidence: 0.9, reasoning: "Contact" },
    },
    {
      turn: 2,
      timestamp: "2026-03-14T10:00:02Z",
      attack: { attack_id: "a2", technique_ids: ["GE-001"], payload: "probe" },
      target_response: { text: "I have access to: search", tool_calls: [] },
      classification: { kill_chain_stage: 1, confidence: 0.85, reasoning: "Probe" },
    },
  ],
};

describe("formatReplay", () => {
  it("should include session metadata", () => {
    const output = formatReplay(mockResult, "my-campaign");
    const parsed = JSON.parse(output);
    expect(parsed.session_id).toBe("test-session");
    expect(parsed.campaign).toBe("my-campaign");
    expect(parsed.max_stage_reached).toBe(2);
    expect(parsed.total_turns).toBe(2);
  });

  it("should include all exchanges with correct fields", () => {
    const output = formatReplay(mockResult);
    const parsed = JSON.parse(output);
    expect(parsed.exchanges).toHaveLength(2);
    expect(parsed.exchanges[0].attack.technique_ids).toEqual(["PI-001"]);
    expect(parsed.exchanges[1].classification.kill_chain_stage).toBe(1);
  });

  it("should omit campaign field when not provided", () => {
    const output = formatReplay(mockResult);
    const parsed = JSON.parse(output);
    expect(parsed.campaign).toBeUndefined();
  });
});
