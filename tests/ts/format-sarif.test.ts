import { describe, it, expect } from "vitest";
import { formatSarif } from "@salt/report-engine";
import type { SessionResult } from "@salt/shared";

const mockResult: SessionResult = {
  session_id: "test-session",
  start_time: "2026-03-14T10:00:00Z",
  end_time: "2026-03-14T10:05:00Z",
  max_stage_reached: 4,
  total_turns: 3,
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
      attack: { attack_id: "a2", technique_ids: ["GE-002"], payload: "probe" },
      target_response: { text: "I have access to search", tool_calls: [] },
      classification: { kill_chain_stage: 1, confidence: 0.85, reasoning: "Probe" },
    },
    {
      turn: 3,
      timestamp: "2026-03-14T10:00:03Z",
      attack: { attack_id: "a3", technique_ids: ["RT-003"], payload: "recon" },
      target_response: { text: "DB_HOST=10.0.0.5", tool_calls: [] },
      classification: { kill_chain_stage: 4, confidence: 0.92, reasoning: "Recon" },
    },
  ],
};

describe("formatSarif", () => {
  it("should produce valid SARIF v2.1.0 structure", () => {
    const output = formatSarif(mockResult);
    const sarif = JSON.parse(output);
    expect(sarif.$schema).toBe("https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json");
    expect(sarif.version).toBe("2.1.0");
    expect(sarif.runs).toHaveLength(1);
  });

  it("should include SALT as the tool driver", () => {
    const sarif = JSON.parse(formatSarif(mockResult));
    expect(sarif.runs[0].tool.driver.name).toBe("SALT");
  });

  it("should only include results for stages > 0", () => {
    const sarif = JSON.parse(formatSarif(mockResult));
    const results = sarif.runs[0].results;
    expect(results).toHaveLength(2); // stage 1 and 4, not stage 0
  });

  it("should map severity levels correctly", () => {
    const sarif = JSON.parse(formatSarif(mockResult));
    const results = sarif.runs[0].results;
    const stage1 = results.find((r: any) => r.ruleId === "GE-002");
    const stage4 = results.find((r: any) => r.ruleId === "RT-003");
    expect(stage1.level).toBe("note");
    expect(stage4.level).toBe("error");
  });

  it("should include kill chain properties", () => {
    const sarif = JSON.parse(formatSarif(mockResult));
    const result = sarif.runs[0].results[1];
    expect(result.properties.killChainStage).toBe(4);
    expect(result.properties.confidence).toBe(0.92);
  });
});
