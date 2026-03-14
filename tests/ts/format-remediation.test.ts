import { describe, it, expect } from "vitest";
import { formatRemediation } from "@salt/report-engine";
import type { SessionResult, Technique } from "@salt/shared";

const techniques: Technique[] = [
  {
    id: "PI-001", category: "prompt_injection", subcategory: "direct",
    name: "Direct instruction override", target_stages: [0, 1],
    template: "", placeholders: [],
    remediation: "Implement input validation that detects instruction override patterns.",
  },
  {
    id: "GE-001", category: "guardrail_erosion", subcategory: "incremental_role_shift",
    name: "Incremental role shifting", target_stages: [1, 2],
    template: "", placeholders: [],
    remediation: "Enforce immutable role definitions.",
  },
  {
    id: "RT-003", category: "recon_tasking", subcategory: "env_extraction",
    name: "Environment variable extraction", target_stages: [3, 4, 5],
    template: "", placeholders: [],
    remediation: "Never expose environment variables.",
  },
];

const mockResult: SessionResult = {
  session_id: "test-session",
  start_time: "2026-03-14T10:00:00Z",
  end_time: "2026-03-14T10:05:00Z",
  max_stage_reached: 4,
  total_turns: 3,
  exchanges: [
    {
      turn: 1, timestamp: "2026-03-14T10:00:01Z",
      attack: { attack_id: "a1", technique_ids: ["PI-001"], payload: "t" },
      target_response: { text: "Hello", tool_calls: [] },
      classification: { kill_chain_stage: 0, confidence: 0.9, reasoning: "Contact" },
    },
    {
      turn: 2, timestamp: "2026-03-14T10:00:02Z",
      attack: { attack_id: "a2", technique_ids: ["GE-001"], payload: "t" },
      target_response: { text: "ok", tool_calls: [] },
      classification: { kill_chain_stage: 2, confidence: 0.78, reasoning: "Erosion" },
    },
    {
      turn: 3, timestamp: "2026-03-14T10:00:03Z",
      attack: { attack_id: "a3", technique_ids: ["RT-003"], payload: "t" },
      target_response: { text: "DB=x", tool_calls: [] },
      classification: { kill_chain_stage: 4, confidence: 0.92, reasoning: "Recon" },
    },
  ],
};

describe("formatRemediation", () => {
  it("should generate Markdown with session header", () => {
    const md = formatRemediation(mockResult, techniques);
    expect(md).toContain("# SALT Remediation Report");
    expect(md).toContain("test-session");
    expect(md).toContain("4/5");
  });

  it("should group by severity", () => {
    const md = formatRemediation(mockResult, techniques);
    expect(md).toContain("## Critical (Stage 4-5)");
    expect(md).toContain("## Warning (Stage 2-3)");
  });

  it("should include remediation text from techniques", () => {
    const md = formatRemediation(mockResult, techniques);
    expect(md).toContain("Never expose environment variables.");
    expect(md).toContain("Enforce immutable role definitions.");
  });

  it("should not include stage 0 techniques", () => {
    const md = formatRemediation(mockResult, techniques);
    expect(md).not.toContain("PI-001");
  });

  it("should sort deepest first", () => {
    const md = formatRemediation(mockResult, techniques);
    const criticalIdx = md.indexOf("Critical");
    const warningIdx = md.indexOf("Warning");
    expect(criticalIdx).toBeLessThan(warningIdx);
  });
});
