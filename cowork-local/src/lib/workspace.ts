import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

/** Prompt for a folder and set it as the agent's sandboxed workspace. */
export async function pickWorkspace(): Promise<string | null> {
  const selected = await open({ directory: true, multiple: false });
  if (typeof selected !== "string") return null;
  await invoke("set_workspace", { path: selected });
  return selected;
}

/** Returns the current workspace path, or null if none is set. */
export async function getWorkspace(): Promise<string | null> {
  return invoke<string | null>("get_workspace");
}
