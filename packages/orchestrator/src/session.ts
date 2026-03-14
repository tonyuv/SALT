import { randomUUID } from "node:crypto";
import { SidecarClient } from "@salt/shared";
import type {
  SessionConfig,
  SessionResult,
  Exchange,
  TargetResponse,
} from "@salt/shared";
import { KillChainTracker, KillChainStage } from "@salt/kill-chain";
import { BlackBoxAdapter } from "@salt/target-interface";

export class Session {
  private config: SessionConfig;
  private sidecarClient: SidecarClient;
  private targetAdapter: BlackBoxAdapter;
  private tracker: KillChainTracker;

  constructor(config: SessionConfig) {
    this.config = config;
    this.sidecarClient = new SidecarClient(config.sidecarPort);
    this.targetAdapter = new BlackBoxAdapter({
      endpoint: config.targetEndpoint,
      responseField: config.responseField ?? "response",
      messageField: config.messageField ?? "message",
      auth: config.targetAuth,
    });
    this.tracker = new KillChainTracker();
  }

  async run(): Promise<SessionResult> {
    const sessionId = randomUUID();
    const startTime = new Date().toISOString();
    const exchanges: Exchange[] = [];
    const deadline = Date.now() + this.config.timeLimitMs;

    for (let turn = 1; turn <= this.config.maxAttempts; turn++) {
      if (Date.now() > deadline) break;

      // 1. Get attack from adversarial agent
      const attack = await this.sidecarClient.attack();

      // 2. Send to target
      const targetResponse = await this.targetAdapter.send(attack.payload);

      // 3. Evaluate response
      const evaluation = await this.sidecarClient.evaluate(
        attack.attack_id,
        targetResponse.text,
        targetResponse.tool_calls
      );

      // 4. Record kill chain progression
      this.tracker.record(
        turn,
        evaluation.kill_chain_stage as KillChainStage,
        evaluation.confidence
      );

      // 5. Log exchange
      exchanges.push({
        turn,
        timestamp: new Date().toISOString(),
        attack,
        target_response: targetResponse,
        classification: evaluation,
      });

      // 6. Stop early if full kill chain reached
      if (evaluation.kill_chain_stage >= KillChainStage.Exfiltration) {
        break;
      }
    }

    // End-of-session training step
    await this.sidecarClient.train(sessionId);

    const progression = this.tracker.getProgression();

    return {
      session_id: sessionId,
      start_time: startTime,
      end_time: new Date().toISOString(),
      max_stage_reached: progression.maxStageReached,
      total_turns: exchanges.length,
      exchanges,
    };
  }
}
