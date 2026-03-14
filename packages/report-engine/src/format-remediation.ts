import type { SessionResult, Technique } from "@salt/shared";

interface FindingEntry {
  techniqueId: string;
  name: string;
  stage: number;
  confidence: number;
  remediation: string;
}

export function formatRemediation(
  result: SessionResult,
  techniques: Technique[]
): string {
  const techniqueMap = new Map(techniques.map((t) => [t.id, t]));

  const findings: FindingEntry[] = [];
  for (const ex of result.exchanges) {
    if (ex.classification.kill_chain_stage < 1) continue;

    const techId = ex.attack.technique_ids[0];
    const tech = techniqueMap.get(techId);
    if (!tech) continue;

    // Keep highest stage per technique
    const existing = findings.find((f) => f.techniqueId === techId);
    if (existing) {
      if (ex.classification.kill_chain_stage > existing.stage) {
        existing.stage = ex.classification.kill_chain_stage;
        existing.confidence = ex.classification.confidence;
      }
    } else {
      findings.push({
        techniqueId: techId,
        name: tech.name,
        stage: ex.classification.kill_chain_stage,
        confidence: ex.classification.confidence,
        remediation: tech.remediation,
      });
    }
  }

  // Sort deepest first
  findings.sort((a, b) => b.stage - a.stage);

  const critical = findings.filter((f) => f.stage >= 4);
  const warning = findings.filter((f) => f.stage >= 2 && f.stage <= 3);
  const info = findings.filter((f) => f.stage === 1);

  const lines: string[] = [
    "# SALT Remediation Report",
    "",
    `Session: ${result.session_id}`,
    `Max Kill Chain Stage Reached: ${result.max_stage_reached}/5`,
    "",
  ];

  if (critical.length > 0) {
    lines.push("## Critical (Stage 4-5)", "");
    for (const f of critical) {
      lines.push(`### ${f.techniqueId}: ${f.name}`);
      lines.push(`- **Stage reached:** ${f.stage}`);
      lines.push(`- **Confidence:** ${f.confidence.toFixed(2)}`);
      lines.push(`- **Remediation:** ${f.remediation}`);
      lines.push("");
    }
  }

  if (warning.length > 0) {
    lines.push("## Warning (Stage 2-3)", "");
    for (const f of warning) {
      lines.push(`### ${f.techniqueId}: ${f.name}`);
      lines.push(`- **Stage reached:** ${f.stage}`);
      lines.push(`- **Confidence:** ${f.confidence.toFixed(2)}`);
      lines.push(`- **Remediation:** ${f.remediation}`);
      lines.push("");
    }
  }

  if (info.length > 0) {
    lines.push("## Info (Stage 1)", "");
    for (const f of info) {
      lines.push(`### ${f.techniqueId}: ${f.name}`);
      lines.push(`- **Stage reached:** ${f.stage}`);
      lines.push(`- **Confidence:** ${f.confidence.toFixed(2)}`);
      lines.push(`- **Remediation:** ${f.remediation}`);
      lines.push("");
    }
  }

  return lines.join("\n");
}
