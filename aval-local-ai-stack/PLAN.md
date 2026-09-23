# AVAL Local AI Stack: Plan

Status: **draft for review**, 2026-09-23. Nothing here has been run on a real Mac or Windows PC yet. The scripts were written and syntax-checked on Linux only. Phase 1 below is where they get tested.

---

## 1. The short version

| Layer | Choice | Why |
|---|---|---|
| Model runtime | **Ollama** (local server on `127.0.0.1:11434`) | Runs on macOS and Windows, open source (MIT), one command to pull a model, local-only mode switch. |
| Interface ("Cowork-like") | **goose Desktop** | Open-source desktop agent that reads and edits files, runs tasks, uses MCP extensions, and supports shareable "recipes". Ollama is a first-class provider. Governed by the Linux Foundation's Agentic AI Foundation since April 2026. |
| Models | **One model family, sized to each machine's RAM** (see `models.conf`) | "Identical everywhere" is not possible across 8 GB and 64 GB machines. Same family keeps behavior as close as hardware allows. |
| Config source of truth | **This repo** (`versions.conf`, `models.conf`, `config/`) | Every machine is built from the same tagged release. Changing a file here and cutting a release is how the team updates. |
| Install and update | **One double-click script per OS** (`Install-AVAL-AI.command` / `Install-AVAL-AI.bat`) | Idempotent: the same script installs, repairs, and updates. |
| Verification | **`verify` script** run at the end of every install/update | Prints PASS/FAIL for each security control, so you can ask people to paste the output. |

What team members get: open **goose**, pick a folder, and talk to a local model that can read and write files in that folder. goose asks before every file write or command.

---

## 2. Where I disagree with the brief

These are the weak points in the request. Each needs a decision from you (collected in [`docs/QUESTIONS.md`](docs/QUESTIONS.md)).

### 2.1 "Most secure possible" conflicts with "like Cowork"
Cowork's value is that the agent acts on your files and runs tools. That is also the attack surface. Indirect prompt injection (instructions hidden in a document the agent reads) can steer an agent into running commands or leaking data. **[Consensus among security researchers that this is an unsolved problem; no defense is complete.]** See Greshake et al. (2023) and the AgentDojo benchmark (Debenedetti et al., 2024), both linked in §8.

The most secure configuration is chat-only (goose's "Chat Only" mode: no file or shell access). This plan's default is the next step up: **Manual Approval**, where the agent must ask before every tool call. goose ships in **Completely Autonomous** mode by default (goose docs, `goose-permissions.md`), so leaving defaults alone would be the wrong call.

### 2.2 "Same configuration on every machine" is only partly achievable
Software, settings, extension allowlist, and approval mode can be identical. The **model** cannot. An 8 GB laptop cannot hold the model a 64 GB machine runs. Different model sizes give different answers to the same prompt. For a research lab this matters: if two analysts code the same transcripts on different machines, their outputs are not comparable. If you need reproducibility, pick one model that fits the *smallest* machine and accept lower quality everywhere, or run a single shared, larger model (see Q3).

### 2.3 Local models will not match Claude in Cowork
Expect a clear capability drop, especially on multi-step agent tasks with many tool calls. I could not find a peer-reviewed head-to-head of current local models versus current frontier models on agentic office tasks, so treat this as **[No reliable peer-reviewed evidence; my expectation based on public leaderboards, unverified]**. The pilot in Phase 1 exists to measure this on AVAL's real tasks before rollout.

On compression, 4-bit quantized models (what Ollama serves by default) score close to full precision on standard benchmarks, but individual answers change, and reasoning and math degrade more. **[Majority view.]** Dissent: Dutta et al. (2024) show that matching accuracy hides many flipped answers, and a 2025 study finds quantization hurts reasoning models on hard tasks. Links in §8.

### 2.4 "Local" does not mean "approved for P3/P4 data"
Running on-device removes the vendor from the data path. It does not by itself satisfy UC IS-3, your data use agreements with CDPH, DCFS, or other partners, or IRB protocols. UCLA's AI tool matrix currently restricts most tools to P1–P2 data (UCLA DTS). Get a written answer from the UCLA Information Security Office and check each DUA before anyone puts client-level data in this stack. **This is the single biggest risk in the project, and it is not technical.** For the restricted version designed for P3 on UCLA-managed laptops, see [`docs/SECURE-LAPTOP-PLAN.md`](docs/SECURE-LAPTOP-PLAN.md).

### 2.5 Ollama on Windows has an open updater problem
Two 2026 CVEs (CVE-2026-42248, CVE-2026-42249) let an attacker who can tamper with the update download plant code that runs at every login, because the Windows updater skipped signature verification. Reports say a fix was merged on May 11, 2026. I could not confirm a tagged release that contains it as of today. The Windows installer here therefore **turns off Ollama's tray app and auto-updater**, runs only `ollama serve` as a logon task, and updates Ollama through winget on our schedule. Re-check before rollout (Q7).

A separate critical bug, "Bleeding Llama" (CVE-2026-7482), leaked server memory through a malicious model file and was fixed in Ollama 0.17.1. The scripts refuse anything older.

---

## 3. Architecture

```
┌──────────────────────── each team member's Mac or PC ────────────────────────┐
│                                                                              │
│   goose Desktop  ──(HTTP, loopback only)──►  Ollama server 127.0.0.1:11434   │
│   • Manual Approval mode                     • OLLAMA_NO_CLOUD=1             │
│   • telemetry off                            • disable_ollama_cloud: true    │
│   • extension allowlist (GOOSE_ALLOWLIST)    • no tray app / auto-updater    │
│   • prompt-injection heuristic on            • version ≥ floor in repo       │
│   • team recipes from this org's repo        • models pinned by ID           │
│                                                                              │
│   OS controls: FileVault / BitLocker on, OS updates on, firewall on          │
└──────────────────────────────────────────────────────────────────────────────┘
                 ▲
                 │ tagged release zip (with SHA-256) from this repo
                 │
           AVAL maintainer: tests on a pilot machine, updates versions.conf /
           models.conf / config, tags a release, emails the team the link.
```

Nothing listens on the network. The only outbound traffic is (a) downloading apps and models during install or update, and (b) whatever the user explicitly approves inside goose.

---

## 4. Security controls and what each one stops

| # | Control | Threat it addresses | Where |
|---|---|---|---|
| 1 | Ollama bound to `127.0.0.1` only (explicit, and checked) | Other machines on café or campus Wi-Fi reaching an unauthenticated model API. Internet scans report on the order of 10⁵ exposed Ollama servers (SecurityWeek, 2026; estimate, not audited). | install scripts, `verify` |
| 2 | Ollama cloud disabled two ways | A model name that silently routes prompts to Ollama's cloud | `config/ollama/server.json`, env var |
| 3 | Minimum Ollama version | Known CVEs (Bleeding Llama) | `versions.conf` |
| 4 | Windows: no tray app, no auto-update | CVE-2026-42248/42249 updater chain | `scripts/windows/install.ps1` |
| 5 | Models only from the manifest, checked by ID | Swapped or tampered model files; drift between machines | `models.conf`, `verify` |
| 6 | goose Manual Approval mode | Agent running commands or overwriting files on its own, including after prompt injection | `config/goose/config.yaml` |
| 7 | goose extension allowlist | Installing a malicious MCP server. One scan found tool poisoning in 5.5% of 1,899 open-source MCP servers (Hasan et al., 2025; preprint) | `config/goose/allowlist.yaml` |
| 8 | goose telemetry off, prompt-injection heuristic on | Usage data leaving the machine; obvious injected commands | `config/goose/config.yaml` |
| 9 | Release zip + published SHA-256; no `curl | bash` | Tampered installer | `docs/MAINTAINER.md` |
| 10 | Full-disk encryption and OS auto-update checked | Stolen laptop; unpatched OS | `verify` (warns, cannot fix) |

What this stack does **not** protect against: a user approving a harmful action, a compromised OS, a malicious model that behaves normally until triggered, or data policy violations. Training (Phase 2) covers the first; UCLA endpoint management covers the second.

---

## 5. Rollout

**Phase 0: Decisions (you, ~1 week).** Answer [`docs/QUESTIONS.md`](docs/QUESTIONS.md). Q1 (data classification) and Q2 (managed devices) can change the whole design.

**Phase 1: Pilot (2–3 people, ~2 weeks).**
1. Run the installer on one Mac and one Windows PC you control. Fix whatever breaks, since the scripts are untested on real hardware.
2. Record the tested Ollama and goose versions and model IDs in `versions.conf` / `models.conf`.
3. Build a 15–20 item task set from real AVAL work at P1 data level (summarize a report, draft an email, clean a CSV, code open-ended responses). Run each task on each tier and have a person score it against Claude. This is the evidence for whether the stack is worth rolling out, and for which tasks.
4. Tag release `v1.0.0`.

**Phase 2: Team rollout.** Send each person: the release link, the one-page guide for their OS ([Mac](docs/INSTALL-MAC.md), [Windows](docs/INSTALL-WINDOWS.md)), and [`docs/USING-GOOSE.md`](docs/USING-GOOSE.md). Run a 30-minute session on what "Allow" means, and ask everyone to paste their `verify` output back to you.

**Phase 3: Maintenance.** Monthly, or sooner for a security advisory: follow [`docs/MAINTAINER.md`](docs/MAINTAINER.md). Team members re-run the same installer from the new release. Total effort for them: download, double-click, paste the verify output.

---

## 6. Updating: how "easy to update" works

- **Apps:** Homebrew (Mac) and winget (Windows) do the updating, not the apps' own auto-updaters. The installer runs `brew upgrade` / `winget upgrade` and then checks the version floor.
- **Settings:** goose and Ollama settings live in `config/`. The installer backs up the user's existing goose `config.yaml` and writes the team version.
- **Models:** change `models.conf`, cut a release, and the next install run pulls the new model and removes models no longer in the manifest (it asks first).
- **Shared workflows:** goose recipes (reusable prompts plus settings, the closest thing to Cowork plugins or skills) can live in a GitHub repo set by `GOOSE_RECIPE_GITHUB_REPO` (Q6).

---

## 7. What I am unsure about

- **Every script is untested on macOS and Windows.** Written against the Ollama and goose docs as of 2026-09-23 and syntax-checked on Linux only.
- goose's config keys for the Ollama provider (`active_provider` / `providers.ollama`) follow the current docs example for Anthropic. I have not confirmed the Ollama block on a live install.
- Model tags in `models.conf` (`qwen3.5:4b`, `qwen3.5:9b`, `qwen3.6:27b`, `qwen3.6:35b-a3b`) were confirmed on Ollama's library and announcements. Memory fit per tier is my estimate, not measured.
- Whether a patched Ollama for Windows has shipped (see §2.5).
- Whether goose Desktop is on winget. The Windows script downloads the zip from GitHub Releases and checks a SHA-256 you record in `versions.conf`. It refuses to install if that hash is blank.

---

## 8. Sources

Grading follows your evidence tiers. Dated 2026-09-23.

**Security research (peer-reviewed or preprint)**
- Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., & Fritz, M. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. *AISec '23*. https://arxiv.org/abs/2302.12173 (peer-reviewed workshop)
- Debenedetti, E., et al. (2024). AgentDojo: A dynamic environment to evaluate prompt injection attacks and defenses for LLM agents. *NeurIPS 2024 Datasets & Benchmarks*. https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html (peer-reviewed)
- Hasan, M. M., et al. (2025). Model Context Protocol (MCP) at first glance: Studying the security and maintainability of MCP servers. https://arxiv.org/abs/2506.13538 **[Emerging: preprint, single study]**

**Quantization**
- A comprehensive evaluation of quantization strategies for large language models (2024). https://arxiv.org/abs/2402.16775 (4-bit roughly on par on evaluated benchmarks) **[preprint]**
- Dutta, A., et al. (2024). Accuracy is not all you need. https://arxiv.org/abs/2407.09141 (answer "flips" under quantization despite similar accuracy) **[preprint]**
- Quantization hurts reasoning? An empirical study on quantized reasoning models (2025). https://arxiv.org/abs/2504.04823 **[preprint]**

**Vendor and advisory sources (primary, not peer-reviewed)**
- Ollama FAQ (local-only mode, bind address, updates): https://github.com/ollama/ollama/blob/main/docs/faq.mdx
- CVE-2026-42249 advisory (patched version listed as "Unknown" when read): https://github.com/advisories/GHSA-7mp6-jmch-f3fh
- Help Net Security on the Windows updater CVEs: https://www.helpnetsecurity.com/2026/05/05/ollama-windows-vulnerabilities-cve-2026-42248-cve-2026-42249/ (secondary coverage)
- Cyera, "Bleeding Llama" (CVE-2026-7482): https://www.cyera.com/research/bleeding-llama-critical-unauthenticated-memory-leak-in-ollama
- SecurityWeek on exposed Ollama servers: https://www.securityweek.com/critical-bug-could-expose-300000-ollama-deployments-to-information-theft/ (secondary; the count is an estimate)
- goose docs (permissions, allowlist, config, env vars): https://github.com/aaif-goose/goose/tree/main/documentation/docs
- goose repository and governance: https://github.com/aaif-goose/goose
- Gemma 4 model card (Apache 2.0): https://ai.google.dev/gemma/docs/core/model_card_4
- Qwen 3.6 on Ollama: https://ollama.com/library/qwen3.6
- UC classification of information (P1–P4): https://security.ucop.edu/policies/institutional-information-and-it-resource-classification.html
- UCLA DTS available AI tools: https://dts.ucla.edu/initiatives/ai/available-tools
