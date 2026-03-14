#!/usr/bin/env node
import { Command } from "commander";
import { runCommand } from "./commands/run.js";

const program = new Command()
  .name("salt")
  .description("SALT — Security Agent Lethality Testing")
  .version("0.1.0");

program.addCommand(runCommand);

program.parse();
