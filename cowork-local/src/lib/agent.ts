import { chat } from "./ollama";
import {
  APPROVAL_REQUIRED,
  TOOL_SCHEMAS,
  describeCall,
  executeTool,
} from "./tools";
import type { ChatMessage, ToolCall, ToolEvent } from "./types";

export const SYSTEM_PROMPT = `You are Cowork Local, a private AI coworker running entirely on the user's own machine via an open-weights model. You help with real work in a chosen workspace folder.

You have tools to list directories, read files, write files, and run shell commands. Guidelines:
- Inspect before you change: read relevant files before editing them.
- Make the smallest change that accomplishes the task.
- Prefer running commands the user can verify. Destructive commands (write_file, run_command) require the user's explicit approval, so explain what you intend before calling them.
- When you have finished the task, stop calling tools and give a concise summary of what you did.`;

export interface AgentCallbacks {
  // Called as assistant text streams in for the current turn.
  onToken: (text: string) => void;
  // Marks the start of a fresh assistant message bubble.
  onAssistantStart: () => void;
  // A tool call has been requested; UI should render a card.
  onToolEvent: (evt: ToolEvent) => void;
  // Update an existing tool card by id.
  onToolEventUpdate: (id: string, patch: Partial<ToolEvent>) => void;
  // Ask the user to approve a side-effecting call. Resolve true to allow.
  requestApproval: (evt: ToolEvent) => Promise<boolean>;
  // Lets the loop bail out early if the user pressed Stop.
  shouldStop: () => boolean;
}

const MAX_STEPS = 12;

/**
 * Run the agentic loop until the model stops requesting tools, the step
 * budget is exhausted, or the user stops it. Returns the updated transcript.
 */
export async function runAgent(
  model: string,
  history: ChatMessage[],
  cb: AgentCallbacks
): Promise<ChatMessage[]> {
  const messages = [...history];

  for (let step = 0; step < MAX_STEPS; step++) {
    if (cb.shouldStop()) break;

    cb.onAssistantStart();
    const { content, toolCalls } = await chat(model, messages, TOOL_SCHEMAS, {
      onToken: cb.onToken,
      onToolCalls: () => {
        /* surfaced below once the full turn resolves */
      },
    });

    const assistantMsg: ChatMessage = { role: "assistant", content };
    if (toolCalls.length) assistantMsg.tool_calls = toolCalls;
    messages.push(assistantMsg);

    // No tools requested → the model has produced its final answer.
    if (!toolCalls.length) break;

    for (const call of toolCalls) {
      if (cb.shouldStop()) return messages;
      const result = await handleToolCall(call, cb);
      messages.push({
        role: "tool",
        tool_name: call.function.name,
        content: result,
      });
    }
  }

  return messages;
}

async function handleToolCall(call: ToolCall, cb: AgentCallbacks): Promise<string> {
  const { name, arguments: args } = call.function;
  const evt: ToolEvent = {
    id: call.id,
    name,
    args,
    status: "pending",
  };
  cb.onToolEvent(evt);

  if (APPROVAL_REQUIRED.has(name)) {
    const approved = await cb.requestApproval(evt);
    if (!approved) {
      cb.onToolEventUpdate(call.id, { status: "denied" });
      return `The user denied permission to ${describeCall(name, args)}.`;
    }
    cb.onToolEventUpdate(call.id, { status: "approved" });
  }

  try {
    const result = await executeTool(name, args);
    cb.onToolEventUpdate(call.id, { status: "ok", result });
    return result;
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    cb.onToolEventUpdate(call.id, { status: "error", result: message });
    return `Error running ${name}: ${message}`;
  }
}
