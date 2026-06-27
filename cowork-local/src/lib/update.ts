import { invoke, Channel } from "@tauri-apps/api/core";
import type { UpdateEvent } from "./types";

export interface UpdateCallbacks {
  onLine: (text: string) => void;
}

/**
 * Trigger the in-app model updater. Discovers the newest Qwen/GLM models,
 * pulls them, and records the default. Resolves with the preferred model slug.
 */
export async function updateModels(
  primary: string | null,
  cb: UpdateCallbacks
): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const channel = new Channel<UpdateEvent>();
    channel.onmessage = (msg) => {
      switch (msg.event) {
        case "status":
          cb.onLine(msg.data.message);
          break;
        case "progress": {
          const pct = msg.data.percent != null ? ` ${msg.data.percent}%` : "";
          cb.onLine(`${msg.data.model}: ${msg.data.status}${pct}`);
          break;
        }
        case "done":
          cb.onLine(`Default model set to ${msg.data.preferred}.`);
          resolve(msg.data.preferred);
          break;
        case "error":
          reject(new Error(msg.data.message));
          break;
      }
    };
    invoke("update_models", { primary, onEvent: channel }).catch((e) =>
      reject(e instanceof Error ? e : new Error(String(e)))
    );
  });
}
