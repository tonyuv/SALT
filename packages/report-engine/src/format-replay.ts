import type { SessionResult } from "@salt/shared";

export function formatReplay(result: SessionResult, campaignName?: string): string {
  const replay: Record<string, unknown> = {
    session_id: result.session_id,
    ...(campaignName !== undefined ? { campaign: campaignName } : {}),
    exchanges: result.exchanges.map((ex) => ({
      turn: ex.turn,
      timestamp: ex.timestamp,
      attack: {
        technique_ids: ex.attack.technique_ids,
        payload: ex.attack.payload,
      },
      target_response: ex.target_response.text,
      tool_calls: ex.target_response.tool_calls,
      classification: {
        kill_chain_stage: ex.classification.kill_chain_stage,
        confidence: ex.classification.confidence,
        reasoning: ex.classification.reasoning,
      },
    })),
    max_stage_reached: result.max_stage_reached,
    total_turns: result.total_turns,
  };

  return JSON.stringify(replay, null, 2);
}
