import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@salt/shared": path.resolve(__dirname, "packages/shared/src"),
      "@salt/kill-chain": path.resolve(__dirname, "packages/kill-chain/src"),
      "@salt/target-interface": path.resolve(__dirname, "packages/target-interface/src"),
      "@salt/orchestrator": path.resolve(__dirname, "packages/orchestrator/src"),
    },
  },
  test: {
    include: ["tests/ts/**/*.test.ts"],
  },
});
