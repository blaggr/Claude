// Shared types between the agent loop, the Ollama client, and the UI.

export type Role = "system" | "user" | "assistant" | "tool";

export interface ToolCallFunction {
  name: string;
  // Ollama returns already-parsed arguments as an object.
  arguments: Record<string, unknown>;
}

export interface ToolCall {
  // Ollama does not always supply an id; we synthesize one when missing.
  id: string;
  function: ToolCallFunction;
}

export interface ChatMessage {
  role: Role;
  content: string;
  // Present on assistant turns that request tools.
  tool_calls?: ToolCall[];
  // Present on tool-result turns so the model can correlate.
  tool_name?: string;
}

// Tool schema as sent to Ollama (OpenAI-compatible "function" format).
export interface ToolSchema {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: {
      type: "object";
      properties: Record<string, unknown>;
      required?: string[];
    };
  };
}

// Streaming events emitted by the Rust `ollama_chat` command over a Channel.
export type StreamEvent =
  | { event: "token"; data: { content: string } }
  | { event: "toolCalls"; data: { calls: ToolCall[] } }
  | { event: "done"; data: { reason: string } }
  | { event: "error"; data: { message: string } };

export interface CommandResult {
  stdout: string;
  stderr: string;
  code: number | null;
}

// UI-facing record of a single tool invocation and its outcome.
export interface ToolEvent {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "pending" | "approved" | "denied" | "ok" | "error";
  result?: string;
}
