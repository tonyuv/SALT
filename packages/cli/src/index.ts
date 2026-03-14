#!/usr/bin/env node
import { Command } from "commander";
import { runCommand } from "./commands/run.js";
import { campaignCommand } from "./commands/campaign.js";
import { reportCommand } from "./commands/report.js";

const program = new Command()
  .name("salt")
  .description("SALT — Security Agent Lethality Testing")
  .version("0.1.0");

program.addCommand(runCommand);
program.addCommand(campaignCommand);
program.addCommand(reportCommand);

program.parse();
