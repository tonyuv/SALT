import { Command } from "commander";
import { SidecarManager, Session } from "@salt/orchestrator";
import type { SessionConfig } from "@salt/shared";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

export const runCommand = new Command("run")
  .description("Run a single SALT session against a target agent")
  .requiredOption("-t, --target <url>", "Target agent endpoint URL")
  .option("-r, --response-field <field>", "JSON field containing agent response", "response")
  .option("-m, --message-field <field>", "JSON field for sending message", "message")
  .option("-n, --max-attempts <number>", "Maximum attack attempts", "50")
  .option("--timeout <ms>", "Session time limit in milliseconds", "300000")
  .option("--auth-header <header>", "Auth header name")
  .option("--auth-value <value>", "Auth header value")
  .option("-o, --output <path>", "Output JSON report path", ".salt/reports/latest.json")
  .action(async (opts) => {
    console.log("SALT — Security Agent Lethality Testing");
    console.log("========================================\n");

    const sidecarManager = new SidecarManager();

    try {
      console.log("[*] Starting adversarial agent sidecar...");
      const sidecarPort = await sidecarManager.start();
      console.log(`[+] Sidecar ready on port ${sidecarPort}\n`);

      const config: SessionConfig = {
        targetEndpoint: opts.target,
        responseField: opts.responseField,
        messageField: opts.messageField,
        maxAttempts: parseInt(opts.maxAttempts, 10),
        timeLimitMs: parseInt(opts.timeout, 10),
        sidecarPort,
        targetAuth: opts.authHeader
          ? { header: opts.authHeader, value: opts.authValue }
          : undefined,
      };

      console.log(`[*] Target: ${config.targetEndpoint}`);
      console.log(`[*] Max attempts: ${config.maxAttempts}`);
      console.log(`[*] Running session...\n`);

      const session = new Session(config);
      const result = await session.run();

      console.log(`\n[+] Session complete`);
      console.log(`    Turns: ${result.total_turns}`);
      console.log(`    Max kill chain stage: ${result.max_stage_reached}/5`);
      console.log(`    Duration: ${new Date(result.end_time).getTime() - new Date(result.start_time).getTime()}ms`);

      // Write report
      const outputPath = path.resolve(opts.output);
      mkdirSync(path.dirname(outputPath), { recursive: true });
      writeFileSync(outputPath, JSON.stringify(result, null, 2));
      console.log(`\n[+] Report saved to ${outputPath}`);
    } catch (err) {
      console.error(`\n[!] Error: ${err instanceof Error ? err.message : err}`);
      process.exitCode = 1;
    } finally {
      console.log("\n[*] Shutting down sidecar...");
      await sidecarManager.stop();
      console.log("[+] Done");
    }
  });
