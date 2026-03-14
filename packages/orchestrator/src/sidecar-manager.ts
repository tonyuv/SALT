import { spawn, type ChildProcess } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

export class SidecarManager {
  private process: ChildProcess | null = null;
  private port: number | null = null;

  async findFreePort(): Promise<number> {
    return new Promise((resolve, reject) => {
      const server = net.createServer();
      server.listen(0, () => {
        const addr = server.address();
        if (addr && typeof addr === "object") {
          const port = addr.port;
          server.close(() => resolve(port));
        } else {
          reject(new Error("Failed to get port"));
        }
      });
    });
  }

  buildCommand(port: number): { command: string; args: string[] } {
    return {
      command: "python",
      args: [
        "-m",
        "uvicorn",
        "salt_agent.server:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        String(port),
      ],
    };
  }

  async start(): Promise<number> {
    if (this.process) {
      throw new Error("Sidecar already running");
    }

    this.port = await this.findFreePort();
    const { command, args } = this.buildCommand(this.port);

    const agentDir = path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../../agent"
    );

    const venvBin = path.join(agentDir, ".venv", "bin");
    const pathEnv = [venvBin, process.env.PATH].filter(Boolean).join(":");

    this.process = spawn(command, args, {
      cwd: agentDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1", PATH: pathEnv },
    });

    this.process.on("exit", (code) => {
      this.process = null;
    });

    // Wait for sidecar to be ready
    await this.waitForReady(this.port);
    return this.port;
  }

  private async waitForReady(port: number, timeoutMs = 30_000): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const response = await fetch(`http://localhost:${port}/model/status`);
        if (response.ok) return;
      } catch {
        // Not ready yet
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error(`Sidecar failed to start within ${timeoutMs}ms`);
  }

  async stop(): Promise<void> {
    if (this.process) {
      this.process.kill("SIGTERM");
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          this.process?.kill("SIGKILL");
          resolve();
        }, 5_000);
        this.process!.on("exit", () => {
          clearTimeout(timeout);
          resolve();
        });
      });
      this.process = null;
      this.port = null;
    }
  }

  getPort(): number | null {
    return this.port;
  }
}
