import axios, { type AxiosInstance } from "axios";
import type { AttackResult, EvaluationResult, ToolCall } from "./types.js";

export class SidecarClient {
  private client: AxiosInstance;

  constructor(port: number, host = "localhost") {
    this.client = axios.create({
      baseURL: `http://${host}:${port}`,
      timeout: 30_000,
    });
  }

  async attack(): Promise<AttackResult> {
    const { data } = await this.client.post<AttackResult>("/attack", {});
    return data;
  }

  async evaluate(
    attackId: string,
    targetResponse: string,
    toolCalls: ToolCall[]
  ): Promise<EvaluationResult> {
    const { data } = await this.client.post<EvaluationResult>("/evaluate", {
      attack_id: attackId,
      target_response: targetResponse,
      tool_calls: toolCalls,
    });
    return data;
  }

  async train(sessionId: string): Promise<{ loss: number; updated: boolean }> {
    const { data } = await this.client.post("/train", {
      session_id: sessionId,
    });
    return data;
  }

  async status(): Promise<Record<string, unknown>> {
    const { data } = await this.client.get("/model/status");
    return data;
  }
}
