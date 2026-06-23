import { invoke } from "@tauri-apps/api/core";
import type { CommandResult, ToolSchema } from "./types";

// The tool catalog advertised to the model. Keep descriptions tight and
// action-oriented; smaller open models follow concise schemas more reliably.
export const TOOL_SCHEMAS: ToolSchema[] = [
  {
    type: "function",
    function: {
      name: "list_directory",
      description:
        "List files and folders at a path inside the workspace. Use '.' for the workspace root.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Path relative to the workspace root." },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "read_file",
      description: "Read a UTF-8 text file inside the workspace and return its contents.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Path relative to the workspace root." },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "write_file",
      description:
        "Create or overwrite a UTF-8 text file inside the workspace. Parent folders are created as needed.",
      parameters: {
        type: "object",
        properties: {
          path: { type: "string", description: "Path relative to the workspace root." },
          content: { type: "string", description: "Full file contents to write." },
        },
        required: ["path", "content"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "run_command",
      description:
        "Run a shell command in the workspace directory and return stdout/stderr. Requires the user to approve each command.",
      parameters: {
        type: "object",
        properties: {
          command: { type: "string", description: "The shell command line to execute." },
        },
        required: ["command"],
      },
    },
  },
];

// Names of tools whose effects require explicit user approval before running.
export const APPROVAL_REQUIRED = new Set<string>(["run_command", "write_file"]);

function asString(v: unknown, field: string): string {
  if (typeof v !== "string") {
    throw new Error(`Expected string for "${field}"`);
  }
  return v;
}

/**
 * Execute a single tool call against the Rust backend. The backend enforces
 * workspace path-scoping; this layer just marshals arguments and formats the
 * textual result that gets fed back to the model.
 */
export async function executeTool(
  name: string,
  args: Record<string, unknown>
): Promise<string> {
  switch (name) {
    case "list_directory": {
      const entries = await invoke<string[]>("list_directory", {
        path: asString(args.path ?? ".", "path"),
      });
      return entries.length ? entries.join("\n") : "(empty directory)";
    }
    case "read_file":
      return invoke<string>("read_file", { path: asString(args.path, "path") });
    case "write_file": {
      const bytes = await invoke<number>("write_file", {
        path: asString(args.path, "path"),
        content: asString(args.content, "content"),
      });
      return `Wrote ${bytes} bytes to ${asString(args.path, "path")}`;
    }
    case "run_command": {
      const res = await invoke<CommandResult>("run_command", {
        command: asString(args.command, "command"),
      });
      const parts = [`exit code: ${res.code ?? "signal"}`];
      if (res.stdout.trim()) parts.push(`stdout:\n${res.stdout}`);
      if (res.stderr.trim()) parts.push(`stderr:\n${res.stderr}`);
      return parts.join("\n\n");
    }
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

/** A short, human-readable summary of a tool call for the approval prompt. */
export function describeCall(name: string, args: Record<string, unknown>): string {
  switch (name) {
    case "run_command":
      return `Run: ${String(args.command ?? "")}`;
    case "write_file":
      return `Write file: ${String(args.path ?? "")}`;
    default:
      return name;
  }
}
