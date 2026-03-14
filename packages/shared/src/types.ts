export interface ToolCall {
  id: string;
  name: string;
  arguments: string;
  result?: string;
}

export interface TargetResponse {
  text: string;
  tool_calls: ToolCall[];
  raw?: unknown;
}

export interface TargetAdapter {
  send(payload: string): Promise<TargetResponse>;
  reset(): Promise<void>;
}

export interface AttackResult {
  attack_id: string;
  technique_ids: string[];
  payload: string;
}

export interface EvaluationResult {
  kill_chain_stage: number;
  confidence: number;
  reasoning: string;
}

export interface SessionConfig {
  targetEndpoint: string;
  targetAuth?: { header: string; value: string };
  responseField?: string;
  messageField?: string;
  maxAttempts: number;
  timeLimitMs: number;
  sidecarPort: number;
}

export interface SessionResult {
  session_id: string;
  start_time: string;
  end_time: string;
  max_stage_reached: number;
  total_turns: number;
  exchanges: Exchange[];
}

export interface Exchange {
  turn: number;
  timestamp: string;
  attack: AttackResult;
  target_response: TargetResponse;
  classification: EvaluationResult;
}
