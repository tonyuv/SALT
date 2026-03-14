import type { SessionResult } from "@salt/shared";

export function formatJson(result: SessionResult): string {
  return JSON.stringify(result, null, 2);
}
