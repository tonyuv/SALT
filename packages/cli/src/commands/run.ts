import { Command } from "commander";
import { SidecarManager, Session, CampaignManager } from "@salt/orchestrator";
import type { SessionConfig } from "@salt/shared";

export const runCommand = new Command("run")
  .description("Run a SALT session against a target agent")
  .option("-t, --target <url>", "Target agent endpoint URL")
  .option("--campaign <name>", "Run within an existing campaign")
  .option("-r, --response-field <field>", "JSON field containing agent response", "response")
  .option("-m, --message-field <field>", "JSON field for sending message", "message")
  .option("-n, --max-attempts <number>", "Maximum attack attempts", "50")
  .option("--timeout <ms>", "Session time limit in milliseconds", "300000")
  .option("--auth-header <header>", "Auth header name")
  .option("--auth-value <value>", "Auth header value")
  .option("-o, --output <path>", "Output JSON report path")
  .action(async (opts) => {
    console.log("SALT — Security Agent Lethality Testing");
    console.log("========================================\n");

    const campaignManager = new CampaignManager();
    let campaignName: string | undefined;
    let agentPurpose = "";
    let config: SessionConfig;

    if (opts.campaign) {
      const name: string = opts.campaign;
      campaignName = name;
      const campaignConfig = campaignManager.readConfig(name);
      config = {
        targetEndpoint: campaignConfig.target.endpoint,
        responseField: campaignConfig.target.responseField,
        messageField: campaignConfig.target.messageField,
        targetAuth: campaignConfig.target.auth,
        maxAttempts: campaignConfig.maxAttempts,
        timeLimitMs: campaignConfig.timeLimitMs,
        sidecarPort: 0, // Will be set after sidecar starts
      };
      agentPurpose = campaignConfig.agentPurpose;

      campaignManager.acquireLock(name);
      console.log(`[*] Campaign: ${campaignName}`);
    } else if (opts.target) {
      config = {
        targetEndpoint: opts.target,
        responseField: opts.responseField,
        messageField: opts.messageField,
        maxAttempts: parseInt(opts.maxAttempts, 10),
        timeLimitMs: parseInt(opts.timeout, 10),
        sidecarPort: 0,
        targetAuth: opts.authHeader
          ? { header: opts.authHeader, value: opts.authValue }
          : undefined,
      };
    } else {
      console.error("[!] Either --target or --campaign is required.");
      process.exitCode = 1;
      return;
    }

    const sidecarManager = new SidecarManager();

    try {
      console.log("[*] Starting adversarial agent sidecar...");
      const sidecarPort = await sidecarManager.start();
      config.sidecarPort = sidecarPort;
      console.log(`[+] Sidecar ready on port ${sidecarPort}\n`);

      console.log(`[*] Target: ${config.targetEndpoint}`);
      console.log(`[*] Max attempts: ${config.maxAttempts}`);
      console.log(`[*] Running session...\n`);

      const session = new Session({
        config,
        campaignName,
        campaignManager: campaignName ? campaignManager : undefined,
        agentPurpose,
      });
      const result = await session.run();

      console.log(`\n[+] Session complete`);
      console.log(`    Turns: ${result.total_turns}`);
      console.log(`    Max kill chain stage: ${result.max_stage_reached}/5`);
      console.log(`    Duration: ${new Date(result.end_time).getTime() - new Date(result.start_time).getTime()}ms`);

      if (campaignName) {
        console.log(`\n[+] Reports saved to .salt/campaigns/${campaignName}/reports/`);
      } else {
        console.log(`\n[+] Reports saved to .salt/reports/`);
      }
    } catch (err) {
      console.error(`\n[!] Error: ${err instanceof Error ? err.message : err}`);
      process.exitCode = 1;
    } finally {
      if (campaignName) {
        campaignManager.releaseLock(campaignName);
      }
      console.log("\n[*] Shutting down sidecar...");
      await sidecarManager.stop();
      console.log("[+] Done");
    }
  });
