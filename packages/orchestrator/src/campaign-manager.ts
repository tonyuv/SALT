import fs from "node:fs";
import path from "node:path";
import type { CampaignConfig, CampaignSessionEntry } from "@salt/shared";

export interface CreateCampaignOptions {
  endpoint: string;
  responseField: string;
  messageField: string;
  auth?: { header: string; value: string };
  agentPurpose: string;
  maxAttempts: number;
  timeLimitMs: number;
}

export class CampaignManager {
  private baseDir: string;

  constructor(baseDir: string = ".salt") {
    this.baseDir = baseDir;
  }

  getCampaignDir(name: string): string {
    return path.join(this.baseDir, "campaigns", name);
  }

  create(name: string, opts: CreateCampaignOptions): void {
    const dir = this.getCampaignDir(name);
    fs.mkdirSync(path.join(dir, "model"), { recursive: true });
    fs.mkdirSync(path.join(dir, "sessions"), { recursive: true });
    fs.mkdirSync(path.join(dir, "reports"), { recursive: true });

    const config: CampaignConfig = {
      name,
      created: new Date().toISOString(),
      target: {
        endpoint: opts.endpoint,
        responseField: opts.responseField,
        messageField: opts.messageField,
        auth: opts.auth,
      },
      agentPurpose: opts.agentPurpose,
      maxAttempts: opts.maxAttempts,
      timeLimitMs: opts.timeLimitMs,
      sessions: [],
    };

    fs.writeFileSync(path.join(dir, "config.json"), JSON.stringify(config, null, 2));
  }

  readConfig(name: string): CampaignConfig {
    const configPath = path.join(this.getCampaignDir(name), "config.json");
    return JSON.parse(fs.readFileSync(configPath, "utf-8"));
  }

  addSession(name: string, entry: CampaignSessionEntry): void {
    const config = this.readConfig(name);
    config.sessions.push(entry);
    const configPath = path.join(this.getCampaignDir(name), "config.json");
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
  }

  acquireLock(name: string): void {
    const lockPath = path.join(this.getCampaignDir(name), ".lock");
    if (fs.existsSync(lockPath)) {
      const pid = parseInt(fs.readFileSync(lockPath, "utf-8").trim(), 10);
      try {
        process.kill(pid, 0); // Check if process is running
        throw new Error(`Campaign "${name}" is locked by PID ${pid}. Another session may be running.`);
      } catch (e: any) {
        if (e.code === "ESRCH") {
          // Stale lock — process no longer running
          fs.unlinkSync(lockPath);
        } else {
          throw e;
        }
      }
    }
    fs.writeFileSync(lockPath, String(process.pid));
  }

  releaseLock(name: string): void {
    const lockPath = path.join(this.getCampaignDir(name), ".lock");
    if (fs.existsSync(lockPath)) {
      fs.unlinkSync(lockPath);
    }
  }

  writeSessionData(name: string, sessionId: string, result: any): void {
    const sessionDir = path.join(this.getCampaignDir(name), "sessions", sessionId);
    fs.mkdirSync(sessionDir, { recursive: true });
    fs.writeFileSync(path.join(sessionDir, "result.json"), JSON.stringify(result, null, 2));
    // Write log.jsonl — one JSON object per exchange
    const logLines = (result.exchanges ?? []).map((ex: any) => JSON.stringify(ex));
    fs.writeFileSync(path.join(sessionDir, "log.jsonl"), logLines.join("\n") + "\n");
  }

  writeReport(name: string, filename: string, content: string): void {
    const reportsDir = path.join(this.getCampaignDir(name), "reports");
    fs.mkdirSync(reportsDir, { recursive: true });
    fs.writeFileSync(path.join(reportsDir, filename), content);
  }
}
