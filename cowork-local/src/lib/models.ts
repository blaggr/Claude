import { invoke } from "@tauri-apps/api/core";

// Families we prefer as the default, in priority order when versions tie.
const FAMILY_PRIORITY = ["glm", "qwen"];

/** Strip the ":tag" suffix Ollama appends, e.g. "qwen3:latest" -> "qwen3". */
function baseName(model: string): string {
  return model.split(":")[0];
}

/** Parse the version embedded in a model name: "qwen2.5" -> [2,5]. */
function versionParts(name: string): number[] {
  const m = name.match(/[0-9]+(?:\.[0-9]+)*/);
  if (!m) return [0];
  return m[0].split(".").map((n) => parseInt(n, 10));
}

function familyOf(name: string): string | null {
  const lower = name.toLowerCase();
  for (const fam of FAMILY_PRIORITY) {
    if (lower.startsWith(fam)) return fam;
  }
  return null;
}

function compareVersions(a: number[], b: number[]): number {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
}

/**
 * Choose the default model to pre-select. Preference order:
 *   1. The model the updater script recorded (if it's installed).
 *   2. The newest installed model from a preferred family (GLM/Qwen), ranked
 *      by version number.
 *   3. The first installed model.
 */
export async function pickDefaultModel(installed: string[]): Promise<string> {
  if (!installed.length) return "";

  let preferred: string | null = null;
  try {
    preferred = await invoke<string | null>("get_preferred_model");
  } catch {
    preferred = null;
  }
  if (preferred) {
    const match = installed.find(
      (m) => m === preferred || baseName(m) === baseName(preferred!)
    );
    if (match) return match;
  }

  const ranked = installed
    .map((m) => ({ m, fam: familyOf(baseName(m)), v: versionParts(baseName(m)) }))
    .filter((x) => x.fam !== null)
    .sort((a, b) => {
      // Higher version first; break ties by family priority.
      const vc = compareVersions(b.v, a.v);
      if (vc !== 0) return vc;
      return FAMILY_PRIORITY.indexOf(a.fam!) - FAMILY_PRIORITY.indexOf(b.fam!);
    });

  return ranked.length ? ranked[0].m : installed[0];
}
