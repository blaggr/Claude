# AVAL-Cowork: Development Plan

**Draft, 2026-09-23.** A Cowork-style local assistant for AVAL laptops, targeting **P1–P2 data**. It updates itself automatically, lets users switch between several open models, and works fully offline.

AVAL-Cowork is the next version of the standard stack in this repo (`PLAN.md`), not a separate product. For P3, use AVAL-R (`docs/SECURE-LAPTOP-PLAN.md`).

---

## 1. Where the brief needs changing

1. **"Updates automatically" must mean automatically from AVAL's own vetted channel, not from upstream.** Letting each vendor's updater pull the latest build onto every laptop is exactly how the Ollama Windows flaws work (CVE-2026-42248/42249: an updater that ran whatever it downloaded). AVAL-Cowork updates on its own, but only to versions the maintainer tested and **signed**, and it rolls them out in stages (§4). Users do nothing. The maintainer spends about an hour a month.
2. **Auto-updating models changes answers without anyone noticing.** A model update can shift outputs on the same prompt. For a research lab that's a reproducibility problem. The plan pins every model by ID, records which version produced each session, announces model changes, and keeps the previous model for 30 days so work can be re-run.
3. **P2 is realistic; full autonomy is not.** Reading files runs without asking. Writing files and running shell commands always ask. Web and desktop-automation tools are off. The reason is that prompt injection is still unsolved **[Consensus]** (Greshake et al., 2023; Debenedetti et al., 2024).
4. **"Secure enough for P2" still needs a UCLA answer.** Anthropic is approved for P2 on UCLA DTS's AI tools list, but self-hosted open-source tools aren't on it. Ask DTS or the Information Security Office for a written OK. I expect a local, encrypted, loopback-only setup to be easier to approve than a cloud tool, but that's my judgment, not policy.
5. **Several models cost disk and memory.** Each model is roughly 3–20 GB on disk, and normally only one fits in memory at a time. Switching can take seconds to a minute while the new model loads (my estimate, not measured). The model menu is sized to each machine's RAM (§5).

## 2. What users get

- **goose Desktop:** chat plus agent in a desktop app. Choose a folder, ask for a task, approve writes.
- **Model switcher:** click the model name at the bottom of goose → *Change Model* (goose docs) and pick from the AVAL menu. Each model is labeled with what it's good at.
- **AVAL Recipes:** one-click, reusable workflows, the closest match to Cowork skills. Stored locally, so they work offline, and updated automatically.
- **AVAL house rules** loaded into every session through goose's global `.goosehints`: data rules, citation honesty, style.
- **Document tools:** read PDF, Word and Excel files through goose's Computer Controller extension, with its web and desktop-automation tools switched off.
- **Offline by default.** Everything runs locally. Updates happen quietly when the machine is online and are skipped when it isn't.
- **Self-repair.** Every update run puts the security settings back if someone changed them, for example switching goose to autonomous mode.
- **Optional (decision needed):** a clearly labeled **"Claude (online)"** provider for P1–P2 tasks that local models do poorly, only if UCLA's Anthropic approval covers API use (Q3).

## 3. Architecture

```
┌──────────────────────────────── AVAL laptop ────────────────────────────────┐
│                                                                              │
│  goose Desktop  ─── loopback ───►  Ollama (127.0.0.1:11434, cloud disabled)  │
│   • per-tool permissions           • AVAL model menu for this RAM tier       │
│   • AVAL recipes + house rules     • max 1 model loaded at a time            │
│   • allowlisted extensions only                                              │
│                                                                              │
│  aval-updater (runs at login + every 6 h; silent if offline)                  │
│   1. fetch manifest.json + manifest.json.sig from AVAL release channel       │
│   2. verify signature against the AVAL key baked in at install               │
│   3. if newer and this machine's ring is due: download each artifact,        │
│      check SHA-256, install when goose is closed                             │
│   4. sync models (add new, keep previous 30 days), recipes, rules, config    │
│   5. re-apply security settings, run verify, show a notification            │
│                                                                              │
│  Status: ~/.aval/status.json (local only, never uploaded)                    │
└──────────────────────────────────────────────────────────────────────────────┘
            ▲ HTTPS, signed manifest
┌───────────┴──────────────┐
│ AVAL release channel      │  GitHub Releases on the (public, secret-free) repo.
│ manifest.json (+ .sig)    │  Maintainer signs with a hardware-backed SSH key.
│ rings: canary → pilot →   │  Rollback = publish a manifest pointing to the
│        everyone           │  last good version.
└──────────────────────────┘
```

### Key design choices
- **Direct, pinned downloads instead of Homebrew or winget.** The manifest lists an exact URL and SHA-256 for each app on each platform. That gives the same version everywhere, removes the Homebrew install step (easier for users), and bypasses vendor self-updaters.
  - macOS: run the `ollama` binary from inside the pinned app bundle through AVAL's LaunchAgent, and never open the app itself. That keeps its updater from running. Bundle path to be confirmed in Phase 1.
  - Windows: keep the current design (tray app removed, `ollama serve` as a logon task).
- **Signed manifest, verified with `ssh-keygen -Y verify`.** It's built into macOS and Windows 10/11 OpenSSH, so there's nothing extra to install. The maintainer's key lives on a hardware security key (FIDO), so a stolen laptop can't sign a malicious update. A second maintainer key is recommended so updates don't depend on one person. **To verify in Phase 1:** the OpenSSH version shipped with the oldest supported Windows build handles `-Y verify`.
- **Rings.** The maintainer's machine gets a release on day 0, pilot users on day 3, everyone on day 7. A security release can skip straight to "everyone."
- **Offline behavior.** If the manifest can't be reached, the updater exits quietly and the last-known-good setup keeps running. Nothing in the daily workflow needs the internet.
  - Known gap: goose fetches its extension allowlist from a URL at startup, and I don't know how it behaves offline (it may fail open or closed). Phase 3 tests this. Fallback: serve the allowlist from a tiny local file server run by the updater.

## 4. Security baseline for P2

| Control | Setting |
|---|---|
| Disk encryption | Required. Verify reports FAIL without FileVault or BitLocker, and the updater shows a persistent warning |
| Model API | Ollama on `127.0.0.1` only, cloud disabled (`OLLAMA_NO_CLOUD=1` and `server.json`), version floor enforced |
| Vendor auto-updaters | Disabled on both platforms; the AVAL updater replaces them |
| Update integrity | Signed manifest plus SHA-256 on every artifact and model ID; the updater refuses anything unsigned or mismatched |
| goose mode | `approve` as the base, with per-tool overrides (below). Reset on every update run |
| Tool permissions | **Always Allow:** read file, list directory, read PDF/Word/Excel. **Ask Before:** write or edit a file, shell. **Never Allow:** web scrape or fetch, desktop/UI automation, any credential tool |
| Extensions | Built-in `developer`, and `computercontroller` restricted as above. Everything else blocked by the allowlist |
| Telemetry | goose telemetry off, no Ollama account, updater sends nothing |
| House rules | "P1–P2 only", "never run network commands", "say when you don't know" (a reminder, **not** a control: models don't reliably follow instructions) |
| Sessions | Stored locally in goose's SQLite database on the encrypted disk. Retention: see Q5 |

## 5. Model menu (per RAM tier)

One primary family, plus a few specialists. **Tags still to verify:** the Gemma 4 and gpt-oss tag names in Ollama's library, and whether each model fits in memory next to a normal workload. Measure both in the pilot.

| Role | ≤15 GB RAM | 16–31 GB | 32–63 GB | 64 GB+ |
|---|---|---|---|---|
| **Everyday** (default) | qwen3.5:4b | qwen3.5:9b | qwen3.6:27b | qwen3.6:35b-a3b |
| **Fast** (quick edits, triage) | qwen3.5:2b | qwen3.5:4b | qwen3.5:9b | qwen3.5:9b |
| **Reasoning** (harder analysis) | — | gpt-oss:20b (tight) | gpt-oss:20b | gpt-oss:120b (needs ~80 GB) |
| **Vision** (charts, scanned pages) | Gemma 4 E4B | Gemma 4 E4B | Gemma 4 26B MoE | Gemma 4 31B |
| Approx. disk | ~10 GB | ~30 GB | ~60 GB | ~150 GB |

Settings: `OLLAMA_MAX_LOADED_MODELS=1`, so switching unloads the previous model instead of running out of memory. Context length stays at the repo default (16K).

Each model's one-line "best for" label appears in `docs/MODEL-GUIDE.md`, and a recipe (*"Which model should I use?"*) is available inside goose.

## 6. Starter AVAL recipes

Each ships with a note on known weaknesses. Local models are weaker than Claude, so every recipe ends by reminding the user to check the output.

1. **Summarize for a partner:** PDF or Word report → 5 bullets plus a 150-word summary for an agency director.
2. **Open-ended response first pass:** CSV column → a draft codebook and example quotes. Explicitly a first pass; the full coding workflow with reliability checks stays human-led.
3. **Clean a CSV:** trim, standardize dates and categories, save a new file, and log every change.
4. **Meeting notes → action items:** owners, dates, open questions.
5. **Draft an email:** short, plain language, uses AVAL's tone guide.
6. **Table and chart checker:** reads a table or chart image (vision model) and lists any numbers that don't add up.

## 7. Development phases

My duration estimates assume one part-time maintainer. They aren't measured.

### Phase 0: Decisions (1 week)
Answer Q1–Q6 (§9). Get the DTS/ISO position on P2 for self-hosted tools.

### Phase 1: Update channel and updater (2–3 weeks)
- [ ] Replace `versions.conf` and `models.conf` with one `manifest.json`. Its schema covers:
  - stack version and ring dates,
  - per-platform app URLs and SHA-256s,
  - the version floor,
  - the model menu per tier with pinned IDs,
  - the recipe and rules bundle hash,
  - a revoked-versions list.
- [ ] Maintainer tool `release.sh`: builds the recipes/rules bundle, writes the manifest, signs it with the hardware key, and publishes a GitHub Release.
- [ ] `aval-updater` for macOS (bash plus LaunchAgent) and Windows (PowerShell plus a scheduled task). It must:
  - verify the signature before anything else,
  - apply updates atomically,
  - install only when goose is closed,
  - keep the previous model for 30 days,
  - re-apply security settings,
  - run verify,
  - show a native notification (macOS `osascript`, Windows toast).
- [ ] Bootstrap installers: the existing double-click installers shrink to "install the updater and its trusted key, then run it once."
- **Exit:** a fresh machine goes from download to a working goose in one double-click, without Homebrew.

### Phase 2: Cowork features (1–2 weeks)
- [ ] Model menu per tier, `MODEL-GUIDE.md`, and the "which model" recipe.
- [ ] Per-tool permission defaults written to goose's `permission.yaml`. The file format isn't documented in what I read, so it has to be worked out from a configured install.
- [ ] Computer Controller enabled, with web and automation tools set to Never Allow. The exact tool names come from a live install.
- [ ] Global `.goosehints` (AVAL house rules) and the six starter recipes in `~/.config/goose/recipes/`.
- **Exit:** the maintainer completes all six recipes on a tier-2 machine.

### Phase 3: Testing (1–2 weeks). Each test passes or fails.
- [ ] **Offline:** airplane mode. goose, model switching and recipes all work; the updater exits cleanly; the allowlist behavior is recorded.
- [ ] **Update:** a new release reaches the canary on day 0 and pilot machines on day 3 or later, not before.
- [ ] **Rollback:** publish a manifest revoking a version; machines return to the last good one.
- [ ] **Tamper:** a changed byte in the manifest, signature, app zip or model → the updater refuses and keeps the old version.
- [ ] **Drift:** switch goose to autonomous mode or enable a blocked extension; the next updater run restores the setting.
- [ ] **Exposure:** a port scan from another machine finds nothing; the Ollama log confirms cloud is disabled.
- [ ] **Prompt injection:** a test document tells goose to run `curl` → goose asks first (shell is Ask Before), and the user training says Deny.
- [ ] **Offline install:** set up a machine from the USB/zip offline bundle with no internet at all.
- **Exit:** all tests pass on one Mac and one Windows PC.

### Phase 4: Pilot, then rollout (2 weeks + ongoing)
- [ ] 2–3 pilot users. Score the recipes against how the same tasks are done today (time saved, errors found).
- [ ] 30-minute onboarding: model switcher, the Allow/Deny rule, P1–P2 only.
- [ ] Monthly maintainer routine (`docs/MAINTAINER.md`, updated): read advisories, test the new versions, `release.sh`, watch the canary ring.

## 8. What changes in this repo

| Now | AVAL-Cowork |
|---|---|
| `versions.conf`, `models.conf` | `manifest.json` (signed) |
| Homebrew / winget installs | Pinned direct downloads, SHA-256 checked |
| User re-runs the installer to update | `aval-updater`, automatic, in rings |
| `developer` extension only, approve everything | Per-tool permissions + restricted Computer Controller |
| One model per machine | Model menu per tier, switchable in goose |
| No recipes or rules | Local AVAL recipes + global `.goosehints`, auto-updated |
| Online install only | Online installer + offline USB/zip bundle |

## 9. Decisions for you

1. **Make the repo public?** The updater and goose's allowlist both need URLs they can reach without logging in, and the repo contains no secrets. Recommended. The alternative is GitHub Pages or a UCLA web server.
2. **Rings and delays:** 0 / 3 / 7 days, or longer?
3. **Claude (online) option:** add it for P1–P2 when online? That depends on whether UCLA's Anthropic approval covers API keys, and on who pays. Off by default either way.
4. **Hardware floor:** 16 GB+ recommended. Machines at 8 GB get a limited menu and slow responses.
5. **Session retention:** keep goose history indefinitely (current behavior) or auto-delete after 90 days? The updater can do this only if goose offers a supported deletion method (to check), because editing its database directly risks corrupting it.
6. **Who holds the second signing key?**

## 10. Sources (checked 2026-09-23)

- goose docs: tool permissions, `.goosehints`, recipe locations and `GOOSE_RECIPE_PATH`, model switching, Computer Controller, allowlist: https://github.com/aaif-goose/goose/tree/main/documentation/docs
- Ollama FAQ (cloud disable, bind address, `OLLAMA_MAX_LOADED_MODELS`): https://github.com/ollama/ollama/blob/main/docs/faq.mdx
- Windows updater CVEs: https://github.com/advisories/GHSA-7mp6-jmch-f3fh ; https://www.helpnetsecurity.com/2026/05/05/ollama-windows-vulnerabilities-cve-2026-42248-cve-2026-42249/
- Greshake et al. (2023), indirect prompt injection: https://arxiv.org/abs/2302.12173
- Debenedetti et al. (2024), AgentDojo: https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html
- UCLA DTS available AI tools (Anthropic listed at P2 in search summaries; confirm on the page): https://dts.ucla.edu/initiatives/ai/available-tools
- Gemma 4 model card: https://ai.google.dev/gemma/docs/core/model_card_4 ; Qwen 3.6 on Ollama: https://ollama.com/library/qwen3.6
