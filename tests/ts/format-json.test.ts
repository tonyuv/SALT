import { describe, it, expect } from "vitest";
import { formatJson } from "@salt/report-engine";
import type { SessionResult } from "@salt/shared";

const mockResult: SessionResult = {
  session_id: "test-session",
  start_time: "2026-03-14T10:00:00Z",
  end_time: "2026-03-14T10:05:00Z",
  max_stage_reached: 2,
  total_turns: 3,
  exchanges: [
    {
      turn: 1,
      timestamp: "2026-03-14T10:00:01Z",
      attack: { attack_id: "a1", technique_ids: ["PI-001"], payload: "test" },
      target_response: { text: "Hello", tool_calls: [] },
      classification: { kill_chain_stage: 0, confidence: 0.9, reasoning: "Contact" },
    },
  ],
};

describe("formatJson", () => {
  it("should return pretty-printed JSON", () => {
    const output = formatJson(mockResult);
    const parsed = JSON.parse(output);
    expect(parsed.session_id).toBe("test-session");
    expect(parsed.max_stage_reached).toBe(2);
  });

  it("should include all exchanges", () => {
    const output = formatJson(mockResult);
    const parsed = JSON.parse(output);
    expect(parsed.exchanges).toHaveLength(1);
  });
});
