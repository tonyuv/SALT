import { Command } from "commander";
import { readFileSync } from "node:fs";
import path from "node:path";
import { CampaignManager } from "@salt/orchestrator";
import { formatJson, formatReplay, formatSarif, formatRemediation } from "@salt/report-engine";
import type { SessionResult, Technique } from "@salt/shared";

export const reportCommand = new Command("report")
  .description("Regenerate reports from the latest session")
  .requiredOption("--campaign <name>", "Campaign name")
  .action((opts) => {
    const manager = new CampaignManager();
    const config = manager.readConfig(opts.campaign);
    const latestSession = config.sessions[config.sessions.length - 1];

    if (!latestSession) {
      console.error("[!] No sessions found in this campaign.");
      process.exitCode = 1;
      return;
    }

    const resultPath = path.join(
      manager.getCampaignDir(opts.campaign),
      "sessions",
      latestSession.id,
      "result.json"
    );
    const result: SessionResult = JSON.parse(readFileSync(resultPath, "utf-8"));

    let techniques: Technique[] = [];
    try {
      techniques = JSON.parse(readFileSync("agent/library/techniques.json", "utf-8"));
    } catch { /* empty */ }

    manager.writeReport(opts.campaign, "latest.json", formatJson(result));
    manager.writeReport(opts.campaign, "latest-replay.json", formatReplay(result, opts.campaign));
    manager.writeReport(opts.campaign, "latest.sarif", formatSarif(result));
    manager.writeReport(opts.campaign, "latest-remediation.md", formatRemediation(result, techniques));

    console.log(`[+] Reports regenerated for campaign "${opts.campaign}"`);
  });
