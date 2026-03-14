import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { SidecarClient } from "@salt/shared";
import type {
  SessionConfig,
  SessionResult,
  Exchange,
  Technique,
} from "@salt/shared";
import { KillChainTracker, KillChainStage } from "@salt/kill-chain";
import { BlackBoxAdapter } from "@salt/target-interface";
import { formatJson, formatReplay, formatSarif, formatRemediation } from "@salt/report-engine";
import { CampaignManager } from "./campaign-manager.js";

export interface SessionOptions {
  config: SessionConfig;
  campaignName?: string;
  campaignManager?: CampaignManager;
  agentPurpose?: string;
}

export class Session {
  private config: SessionConfig;
  private sidecarClient: SidecarClient;
  private targetAdapter: BlackBoxAdapter;
  private tracker: KillChainTracker;
  private campaignName?: string;
  private campaignManager?: CampaignManager;
  private agentPurpose: string;

  constructor(opts: SessionOptions) {
    this.config = opts.config;
    this.campaignName = opts.campaignName;
    this.campaignManager = opts.campaignManager;
    this.agentPurpose = opts.agentPurpose ?? "";
    this.sidecarClient = new SidecarClient(opts.config.sidecarPort);
    this.targetAdapter = new BlackBoxAdapter({
      endpoint: opts.config.targetEndpoint,
      responseField: opts.config.responseField ?? "response",
      messageField: opts.config.messageField ?? "message",
      auth: opts.config.targetAuth,
    });
    this.tracker = new KillChainTracker();
  }

  async run(): Promise<SessionResult> {
    const sessionId = randomUUID();
    const startTime = new Date().toISOString();
    const exchanges: Exchange[] = [];
    const deadline = Date.now() + this.config.timeLimitMs;

    // Load campaign model weights if applicable
    if (this.campaignName && this.campaignManager) {
      const campaignDir = this.campaignManager.getCampaignDir(this.campaignName);
      await this.sidecarClient.campaignLoad(campaignDir);
    }

    for (let turn = 1; turn <= this.config.maxAttempts; turn++) {
      if (Date.now() > deadline) break;

      const attack = await this.sidecarClient.attack();
      const targetResponse = await this.targetAdapter.send(attack.payload);
      const evaluation = await this.sidecarClient.evaluate(
        attack.attack_id,
        targetResponse.text,
        targetResponse.tool_calls
      );

      this.tracker.record(
        turn,
        evaluation.kill_chain_stage as KillChainStage,
        evaluation.confidence
      );

      exchanges.push({
        turn,
        timestamp: new Date().toISOString(),
        attack,
        target_response: targetResponse,
        classification: evaluation,
      });

      if (evaluation.kill_chain_stage >= KillChainStage.Exfiltration) {
        break;
      }
    }

    // Train
    await this.sidecarClient.train(sessionId, this.agentPurpose);

    // Save campaign model weights if applicable
    if (this.campaignName && this.campaignManager) {
      const campaignDir = this.campaignManager.getCampaignDir(this.campaignName);
      await this.sidecarClient.campaignSave(campaignDir);
    }

    const progression = this.tracker.getProgression();

    const result: SessionResult = {
      session_id: sessionId,
      start_time: startTime,
      end_time: new Date().toISOString(),
      max_stage_reached: progression.maxStageReached,
      total_turns: exchanges.length,
      exchanges,
    };

    // Write reports
    this.writeReports(result);

    // Update campaign session list
    if (this.campaignName && this.campaignManager) {
      this.campaignManager.writeSessionData(this.campaignName, sessionId, result);
      this.campaignManager.addSession(this.campaignName, {
        id: sessionId,
        timestamp: startTime,
        maxStageReached: progression.maxStageReached,
      });
    }

    return result;
  }

  private writeReports(result: SessionResult): void {
    const techniques = this.loadTechniques();

    if (this.campaignName && this.campaignManager) {
      this.campaignManager.writeReport(this.campaignName, "latest.json", formatJson(result));
      this.campaignManager.writeReport(this.campaignName, "latest-replay.json", formatReplay(result, this.campaignName));
      this.campaignManager.writeReport(this.campaignName, "latest.sarif", formatSarif(result));
      this.campaignManager.writeReport(this.campaignName, "latest-remediation.md", formatRemediation(result, techniques));
    } else {
      const reportsDir = ".salt/reports";
      mkdirSync(reportsDir, { recursive: true });
      writeFileSync(path.join(reportsDir, "latest.json"), formatJson(result));
      writeFileSync(path.join(reportsDir, "latest-replay.json"), formatReplay(result));
      writeFileSync(path.join(reportsDir, "latest.sarif"), formatSarif(result));
      writeFileSync(path.join(reportsDir, "latest-remediation.md"), formatRemediation(result, techniques));
    }
  }

  private loadTechniques(): Technique[] {
    try {
      const techniquesPath = path.resolve("agent/library/techniques.json");
      return JSON.parse(readFileSync(techniquesPath, "utf-8"));
    } catch {
      return [];
    }
  }
}
