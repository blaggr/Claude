import { invoke, Channel } from "@tauri-apps/api/core";
import type { ChatMessage, StreamEvent, ToolCall, ToolSchema } from "./types";

// All model traffic goes through the Rust backend, whose only network
// destination is the local Ollama daemon. The frontend never opens a socket.

export interface ChatCallbacks {
  onToken: (text: string) => void;
  onToolCalls: (calls: ToolCall[]) => void;
}

export interface ChatResult {
  content: string;
  toolCalls: ToolCall[];
  doneReason: string;
}

/**
 * Stream one assistant turn from Ollama. Resolves when the turn is complete,
 * returning the accumulated text and any requested tool calls.
 */
export async function chat(
  model: string,
  messages: ChatMessage[],
  tools: ToolSchema[],
  cb: ChatCallbacks
): Promise<ChatResult> {
  let content = "";
  let toolCalls: ToolCall[] = [];

  return new Promise<ChatResult>((resolve, reject) => {
    const channel = new Channel<StreamEvent>();
    channel.onmessage = (msg) => {
      switch (msg.event) {
        case "token":
          content += msg.data.content;
          cb.onToken(msg.data.content);
          break;
        case "toolCalls":
          toolCalls = toolCalls.concat(msg.data.calls);
          cb.onToolCalls(msg.data.calls);
          break;
        case "done":
          resolve({ content, toolCalls, doneReason: msg.data.reason });
          break;
        case "error":
          reject(new Error(msg.data.message));
          break;
      }
    };

    invoke("ollama_chat", { model, messages, tools, onEvent: channel }).catch(
      (e) => reject(e instanceof Error ? e : new Error(String(e)))
    );
  });
}

/** List models installed in the local Ollama instance. */
export async function listModels(): Promise<string[]> {
  return invoke<string[]>("ollama_list_models");
}
