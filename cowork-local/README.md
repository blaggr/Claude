# Cowork Local

A private, desktop "Claude Cowork"-style AI coworker that runs **entirely on your
own machine** using an open-weights model via [Ollama](https://ollama.com).
You chat with it, and it can actually do work in a folder you choose: read and
write files and run shell commands — with every side‑effecting action gated
behind an explicit approval prompt.

No API keys. No cloud. The only network connection the app makes is to the
Ollama daemon on `127.0.0.1`.

---

## Why this is private by design

| Concern | How Cowork Local handles it |
| --- | --- |
| Model inference | Runs locally in Ollama; prompts never leave the machine. |
| App network access | The webview's Content‑Security‑Policy blocks all outbound requests. Only the Rust backend talks to the network, and only to `127.0.0.1:11434`. |
| File access | The agent can only touch files inside the single **workspace folder** you pick. Paths are resolved and validated in Rust to prevent escaping the sandbox (`..`, absolute paths, symlink traversal). |
| Shell / file writes | `run_command` and `write_file` require a per‑action **Approve** click. Nothing runs on your shell or overwrites a file without you seeing the exact command/contents first. |
| Attack surface | Tauri (Rust + system webview), not a bundled browser or a localhost web server. A tight capability allowlist grants the UI only the folder‑picker dialog. |

---

## Prerequisites

1. **Ollama** — install from <https://ollama.com>. Then either pull a model by
   hand, or use the **Qwen/GLM auto-setup** below (recommended). Tool calling
   requires a model that supports it — `qwen3`/`qwen2.5` and `glm4` are good
   tool-capable choices; `llama3.1` and `mistral-nemo` also work.
   Make sure Ollama is running (`ollama serve`, or just launch the app).

2. **Rust** — <https://rustup.rs>
3. **Node.js 18+** and npm.

macOS also needs Xcode Command Line Tools (`xcode-select --install`).

---

## Run the newest Qwen / GLM automatically

Cowork Local can track the **Qwen** and **GLM** model families and keep itself
on the latest release. It works by *discovery*: each run it asks the Ollama
library which `qwen*` / `glm*` base models are published and pulls the
highest-versioned one (e.g. it picks `qwen3` over `qwen2.5`). This is why it
keeps working when a vendor ships a new major version under a new name —
nothing is hardcoded.

> **Note on GLM:** GLM's availability in the official Ollama library is
> intermittent. If no GLM base model is published, the updater says so and
> falls back to Qwen. To run a specific GLM that's only on Hugging Face, import
> its GGUF with `ollama create glm-custom -f Modelfile` and select it in the
> app.

### One-time setup (pull the latest now)

```bash
cd cowork-local
./scripts/setup_models.sh                 # newest Qwen + GLM, default = Qwen
# or make GLM the default when present:
./scripts/setup_models.sh --primary glm
```

The app reads `~/.cowork-local/config.json` and pre-selects the model chosen
here on launch. (If you skip this, the app still auto-selects the newest
Qwen/GLM among whatever you've already installed.)

### Or update from inside the app

Click **Update models** in the top bar. It runs the same discovery natively
(no Python needed), streams pull progress in a panel, and switches the app to
the newest model when it finishes.

### Keep it updated automatically (daily)

Install a macOS LaunchAgent that re-checks and pulls newer releases every day:

```bash
./scripts/install_auto_update.sh                 # daily 03:00, prefer Qwen
./scripts/install_auto_update.sh --primary glm    # prefer GLM
./scripts/install_auto_update.sh --hour 9         # run at 09:00 instead
./scripts/install_auto_update.sh --uninstall      # stop auto-updating
```

It runs once immediately and then on schedule; output goes to
`~/.cowork-local/updater.log`. Check what it's doing any time without pulling:

```bash
python3 scripts/update_models.py --check
```

---

## Run it (development)

```bash
cd cowork-local
npm install
npm run tauri dev
```

The first launch compiles the Rust backend (a few minutes); subsequent launches
are fast. The app window will open automatically.

1. Click **Choose workspace…** and pick a folder you want the agent to work in.
2. Select a model from the top‑right dropdown (populated from your installed
   Ollama models).
3. Ask it to do something, e.g. *"Summarize every Markdown file in this folder
   and write the result to summary.md"* or *"Run the test suite and fix the
   first failure."*
4. When it wants to write a file or run a command, you'll get an approval
   dialog showing exactly what it intends to do.

Press **Stop** at any time to halt the agent loop.

---

## Build a distributable app

Before bundling for macOS/Windows, generate the full platform icon set from a
1024×1024 source image (this creates `.icns`/`.ico` and the required PNGs):

```bash
npm run tauri icon path/to/your-logo.png
```

Then:

```bash
npm run tauri build
```

The installer/app bundle lands in `src-tauri/target/release/bundle/`.

> The repo ships simple placeholder PNG icons (generated by
> `scripts/make_icons.py`) so `tauri dev` works out of the box. Replace them
> with the `tauri icon` step above for a real release.

---

## How it works

```
┌─────────────────────────── Tauri app ───────────────────────────┐
│                                                                  │
│  React UI (webview)            Rust backend (native)             │
│  ─────────────────             ─────────────────────             │
│  • chat + streaming            • ollama_chat  ── HTTP ──▶ Ollama  │
│  • tool cards                  • list_directory / read_file      │
│  • approval dialogs            • write_file   (workspace-scoped) │
│  • agent loop orchestration    • run_command  (workspace cwd)    │
│         │   invoke() / Channel        ▲                          │
│         └───────────────────────────-─┘                          │
└──────────────────────────────────────────────────────────────────┘
```

- **Agent loop** (`src/lib/agent.ts`): sends the transcript + tool schemas to
  Ollama, streams the reply, runs any requested tools (asking for approval when
  needed), feeds results back, and repeats until the model stops calling tools
  (max 12 steps).
- **Model streaming** (`src-tauri/src/ollama.rs`): proxies Ollama's
  newline‑delimited JSON stream to the UI over a Tauri `Channel`, forwarding
  text tokens and tool calls as they arrive.
- **Sandbox** (`src-tauri/src/state.rs`): every path is joined to the workspace
  root, lexically normalized, and rejected if it escapes the root.

### Tools available to the agent

| Tool | Effect | Approval |
| --- | --- | --- |
| `list_directory` | List files/folders in the workspace | auto |
| `read_file` | Read a text file (≤ 2 MiB) | auto |
| `write_file` | Create/overwrite a text file | **required** |
| `run_command` | Run a shell command in the workspace | **required** |

Add your own tools by extending `TOOL_SCHEMAS` and `executeTool` in
`src/lib/tools.ts` and adding the matching Rust `#[tauri::command]`.

---

## Project layout

```
cowork-local/
├── src/                 # React + TypeScript frontend
│   ├── lib/             #   agent loop, ollama client, tools, workspace
│   └── components/      #   chat bubbles, tool cards, approval dialog
├── src-tauri/           # Rust backend
│   └── src/             #   ollama.rs, fs_tools.rs, shell.rs, state.rs, error.rs
└── scripts/make_icons.py
```

---

## Troubleshooting

- **"Could not reach Ollama"** — start Ollama (`ollama serve`) and confirm
  `curl http://127.0.0.1:11434/api/tags` returns JSON.
- **Model ignores tools / never edits files** — use a tool‑calling model
  (`llama3.1`, `qwen2.5`). Older/base models don't emit tool calls.
- **"no models" in the dropdown** — `ollama pull <model>` first.
