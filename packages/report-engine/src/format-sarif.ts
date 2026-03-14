import type { SessionResult } from "@salt/shared";

function stageToLevel(stage: number): string {
  if (stage <= 1) return "note";
  if (stage <= 3) return "warning";
  return "error";
}

export function formatSarif(result: SessionResult): string {
  const relevantExchanges = result.exchanges.filter(
    (ex) => ex.classification.kill_chain_stage > 0
  );

  const ruleIds = [...new Set(relevantExchanges.flatMap((ex) => ex.attack.technique_ids))];

  const rules = ruleIds.map((id) => ({
    id,
    shortDescription: { text: `Attack technique ${id}` },
  }));

  const results = relevantExchanges.map((ex) => ({
    ruleId: ex.attack.technique_ids[0],
    message: { text: ex.classification.reasoning },
    level: stageToLevel(ex.classification.kill_chain_stage),
    properties: {
      killChainStage: ex.classification.kill_chain_stage,
      confidence: ex.classification.confidence,
      turn: ex.turn,
    },
  }));

  const sarif = {
    $schema:
      "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
    version: "2.1.0",
    runs: [
      {
        tool: {
          driver: {
            name: "SALT",
            version: "0.1.0",
            informationUri: "https://github.com/tonyuv/SALT",
            rules,
          },
        },
        results,
      },
    ],
  };

  return JSON.stringify(sarif, null, 2);
}
