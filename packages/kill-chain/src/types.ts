export enum KillChainStage {
  Contact = 0,
  Probe = 1,
  GuardrailErosion = 2,
  TaskDeviation = 3,
  ReconExecution = 4,
  Exfiltration = 5,
}

export interface StageEvent {
  turn: number;
  timestamp: string;
  stage: KillChainStage;
  confidence: number;
}

export interface SessionProgression {
  maxStageReached: KillChainStage;
  stageTimeline: StageEvent[];
  stageFirstReached: Record<number, number>;
}
