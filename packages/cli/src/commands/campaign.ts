import { Command } from "commander";
import { CampaignManager } from "@salt/orchestrator";

export const campaignCommand = new Command("campaign")
  .description("Manage SALT campaigns");

campaignCommand
  .command("create <name>")
  .description("Create a new campaign")
  .requiredOption("-t, --target <url>", "Target agent endpoint URL")
  .option("-r, --response-field <field>", "JSON field containing agent response", "response")
  .option("-m, --message-field <field>", "JSON field for sending message", "message")
  .option("--auth-header <header>", "Auth header name")
  .option("--auth-value <value>", "Auth header value")
  .option("-n, --max-attempts <number>", "Maximum attack attempts", "50")
  .option("--timeout <ms>", "Session time limit in milliseconds", "300000")
  .option("--agent-purpose <text>", "Description of target agent's intended role", "")
  .action((name, opts) => {
    const manager = new CampaignManager();
    manager.create(name, {
      endpoint: opts.target,
      responseField: opts.responseField,
      messageField: opts.messageField,
      auth: opts.authHeader ? { header: opts.authHeader, value: opts.authValue } : undefined,
      agentPurpose: opts.agentPurpose,
      maxAttempts: parseInt(opts.maxAttempts, 10),
      timeLimitMs: parseInt(opts.timeout, 10),
    });
    console.log(`[+] Campaign "${name}" created at .salt/campaigns/${name}/`);
  });
