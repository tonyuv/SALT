import { KillChainStage, type StageEvent, type SessionProgression } from "./types.js";

export class KillChainTracker {
  private maxStage: KillChainStage = KillChainStage.Contact;
  private timeline: StageEvent[] = [];
  private firstReached: Record<number, number> = {};

  record(turn: number, stage: KillChainStage, confidence: number): void {
    const event: StageEvent = {
      turn,
      timestamp: new Date().toISOString(),
      stage,
      confidence,
    };
    this.timeline.push(event);
    if (stage > this.maxStage) {
      this.maxStage = stage;
    }
    if (!(stage in this.firstReached)) {
      this.firstReached[stage] = turn;
    }
  }

  getProgression(): SessionProgression {
    return {
      maxStageReached: this.maxStage,
      stageTimeline: [...this.timeline],
      stageFirstReached: { ...this.firstReached },
    };
  }

  reset(): void {
    this.maxStage = KillChainStage.Contact;
    this.timeline = [];
    this.firstReached = {};
  }
}
