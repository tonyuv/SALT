import axios, { type AxiosInstance } from "axios";
import type { TargetAdapter, TargetResponse } from "@salt/shared";

export interface BlackBoxConfig {
  endpoint: string;
  responseField: string;
  messageField?: string;
  auth?: { header: string; value: string };
}

export class BlackBoxAdapter implements TargetAdapter {
  private client: AxiosInstance;
  private responseField: string;
  private messageField: string;

  constructor(config: BlackBoxConfig) {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (config.auth) { headers[config.auth.header] = config.auth.value; }
    this.client = axios.create({ baseURL: config.endpoint, timeout: 60_000, headers });
    this.responseField = config.responseField;
    this.messageField = config.messageField ?? "message";
  }

  async send(payload: string): Promise<TargetResponse> {
    const { data } = await this.client.post("/", { [this.messageField]: payload });
    return { text: String(data[this.responseField] ?? ""), tool_calls: [] };
  }

  async reset(): Promise<void> { }
}
