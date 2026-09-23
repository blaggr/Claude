# AVAL-R: Restricted Local AI Profile for UCLA-Managed Laptops

**Development plan, draft 2026-09-23.** For review by Rob, AVAL's maintainer, UCLA IT (endpoint team), and the UCLA Information Security Office (ISO).

**What this is:** the most locked-down version of the AVAL local AI stack that can run on an individual UCLA laptop, designed so it has a realistic chance of ISO approval for **P3** data.

**What this is not:** an approval. P3 use starts only after the ISO risk assessment, IRB amendment, and DUA review in Phase 0 come back positive. **P4 stays off laptops.** Use the High Compliance Environment (HCE) path instead (see §9).

---

## 1. Design principle: take away every way data can leave

On a laptop, the ways P3 data escapes are: the network, the agent running commands, the browser loading external content, sync clients, logs and chat history on disk, and people. The standard AVAL stack reduces these. AVAL-R **removes** each one that software can remove, and enforces the removal at the operating-system level, where a user or a hijacked model cannot switch it back.

This costs the Cowork-like experience. **AVAL-R is a chat assistant, not an agent.** It cannot read folders, run commands, or edit files. Users paste text or attach a file to a chat, and copy results out. The reason is that indirect prompt injection is an unsolved problem **[Consensus]**: instructions hidden in a document can steer a tool-using model into running commands or leaking data (Greshake et al., 2023; Debenedetti et al., 2024). With no tools and no network, a hijacked model can still produce a wrong or misleading answer, but it has no channel to send data anywhere.

## 2. What changes from the standard stack

| Area | Standard AVAL stack | AVAL-R | Why |
|---|---|---|---|
| Device | Any Mac or PC | **UCLA-managed only** (Jamf or Intune, UCLA EDR, enforced FileVault or BitLocker, no local admin) | UC minimum standards expect IT-managed devices with EDR and severity-based patching for P3/P4 |
| Installed by | User, double-click | **IT, via MDM**, as signed packages | Users can't change or remove controls |
| Model runtime | Ollama | **llama.cpp `llama-server`**, pinned build | No cloud features, no model-download API, no self-updater. Supports an API key, `--offline`, and turning off its MCP proxy |
| Runs as | Logged-in user | **Dedicated low-privilege service account** | User processes can't alter the server or its model files |
| Network | Loopback only | Loopback only, **plus an OS-level outbound block** on the server account and `--offline` | Even a compromised server can't phone out |
| API access | Unauthenticated | **Per-machine API key** | Blocks drive-by requests from web pages (DNS-rebinding class; Ollama had one, CVE-2024-28224) |
| Interface | goose Desktop (agent) | **llama-server's built-in chat UI**, served locally behind a proxy that sets a strict Content-Security-Policy, opened in a managed browser profile | goose has no admin lock (users can switch modes and add extensions). The server-side UI has no tool execution. The CSP stops model output from loading external images, a documented exfiltration path |
| Models | Pulled from the internet by the user | **Delivered by IT inside the package**, SHA-256 pinned, read-only | Crafted GGUF files have triggered memory bugs in llama.cpp's parser (CVE-2026-27940, CVE-2026-33298) and in Ollama's (CVE-2026-7482). Only vetted files are ever loaded |
| Chat history | goose SQLite database, kept indefinitely | **In the managed browser profile, wiped on a schedule** (default: on close + daily) | History is P3 data at rest |
| Server logs | Default | **Metadata only, verified to contain no prompt text** | Logs must not become an unmanaged copy of P3 data |
| Files | Any folder | **One work folder excluded from Box, Drive, OneDrive, and iCloud sync** | Sync clients are a network path |
| Updates | User re-runs installer | **IT pushes monthly, plus emergency patches** | Patching must be timely and uniform |
| Compliance check | User runs verify, pastes output | **MDM runs the check every day and reports drift to IT** | Monitoring can't depend on users |

## 3. Architecture

```
┌──────────────────── UCLA-managed laptop (Jamf / Intune + EDR) ─────────────────────┐
│                                                                                     │
│  Managed browser profile "AVAL-R"                                                    │
│   • no extensions, no sync, history cleared on close and daily                       │
│   • opens http://127.0.0.1:8081 only                                                 │
│            │                                                                         │
│            ▼                                                                         │
│  aval-r-proxy (127.0.0.1:8081)       ── adds CSP: default-src 'self'; img-src 'self'  │
│            │                            data: blob:; connect-src 'self'; frame-      │
│            ▼                            ancestors 'none'                             │
│  llama-server (127.0.0.1:8080, service account _avalr)                               │
│   • --host 127.0.0.1 --api-key-file <root-owned> --offline                           │
│   • --no-ui-mcp-proxy, --no-slots, no --metrics, no --slot-save-path                 │
│   • model: /Library/AVAL-R/models/<pinned>.gguf  (read-only, SHA-256 checked)        │
│   • OS firewall: all outbound traffic blocked for _avalr                             │
│                                                                                     │
│  Work folder: ~/AVAL-R-Work (excluded from every sync client)                        │
│  Daily MDM compliance script → IT dashboard (no content, settings and hashes only)   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Why add a proxy?** I found no documented option in `llama-server` for setting response headers. A proxy of about 50 lines (or an equivalent patch to llama.cpp) is the most reliable way to guarantee the CSP. Phase 2 checks whether the built-in UI already sanitizes model output. The CSP stays either way, as a second layer.

## 4. Threat model

| # | Threat | Control | Residual risk |
|---|---|---|---|
| T1 | Stolen or lost laptop | Enforced disk encryption, MDM remote wipe, screen lock | Low, while the device is locked |
| T2 | Other devices on the network reach the model | Loopback-only bind, API key, verified by port scan | Low |
| T3 | A malicious web page calls the local API | API key; CSP and `frame-ancestors`; DNS-rebinding test | Low |
| T4 | Prompt injection leads to command execution | No tools exist in AVAL-R | Negligible |
| T5 | Prompt injection leaks data through a rendered image or link | CSP blocks external loads; test in Phase 2 | Low. A user could still click a malicious *link*, so training covers links |
| T6 | Server or model phones home | `--offline`, outbound block on the service account, EDR network telemetry | Low |
| T7 | Malicious or tampered model file | IT-only delivery, SHA-256 pin, read-only files, weights from major publishers only | Low for tampering. Backdoored weights are a research-stage risk (Hubinger et al., 2024 show backdoors can survive safety training) **[Emerging]**, and having no tools limits what one could do |
| T8 | P3 data persists in history or logs | Scheduled wipe of browser storage; log content test | Medium until the wipe is verified |
| T9 | P3 data leaks through sync or copy-paste | Work folder excluded from sync; MDM restrictions where available; training | **Medium: people are the main remaining risk** |
| T10 | Unpatched llama.cpp vulnerability | Monthly IT patch cycle, advisory watch, emergency path | Medium; the parser has had several 2026 CVEs |
| T11 | Wrong or made-up output used in research | Human review; output labeled "draft, unverified" | Not a security control. Handled in the data SOP |

## 5. Development phases

Durations are my estimates for one part-time AVAL maintainer plus IT support. They are not measured.

### Phase 0: Approval gate (2–6 weeks; mostly waiting on others)
- [ ] Send this plan to ISO and your unit's information security lead. Request an IS-3 risk assessment for "local LLM inference on managed endpoints, P3."
- [ ] List every dataset intended for AVAL-R. For each one, record its classification, DUA clauses on software, location and processing, and IRB protocol.
- [ ] IRB: amend affected protocols to name local AI processing.
- [ ] IT: confirm the MDM platform, EDR product, whether per-account outbound firewall rules are possible on macOS (pf or EDR policy), and packaging requirements.
- **Exit:** a written ISO answer (go, go with conditions, or no) and a dataset list. If ISO says no, stop, or move to the HCE path.

### Phase 1: Build (3–4 weeks)
- [ ] **Runtime package.** Pin a llama.cpp release. Build it from the tagged source in CI, or use the official release binary with a recorded hash. Produce a macOS `.pkg` and a Windows `.msi`/`.intunewin`, both signed with a UCLA code-signing identity.
- [ ] **Service wrapper.** macOS: a LaunchDaemon running as `_avalr`. Windows: a service under a virtual account (`NT SERVICE\AVAL-R`) using a vetted service wrapper. The server reads its API key from a file that only it and the installer can read.
- [ ] **Outbound block.** macOS: a pf anchor blocking outbound traffic for user `_avalr`, or the equivalent EDR firewall policy. Windows: a Defender Firewall outbound block rule for `llama-server.exe`, set by Intune.
- [ ] **CSP proxy.** A minimal loopback reverse proxy that adds the CSP and `X-Content-Type-Options`. Keep it dependency-free, audit it, and ship it in the same package.
- [ ] **Model package.** One or two models chosen in the pilot, as GGUF files with a SHA-256 manifest, installed read-only. The service refuses to start if a hash doesn't match.
- [ ] **Browser profile.** Managed Chrome or Edge policy for an "AVAL-R" profile: no extensions, no sign-in or sync, clear-on-exit for its site data, start page `http://127.0.0.1:8081`. Add a desktop shortcut that opens it.
- [ ] **Work folder.** Create it and add it to the exclusion policy of every sync client IT supports.
- [ ] **Compliance script.** Runs daily from MDM (Jamf extension attribute or Intune remediation) and reports PASS/FAIL, never content, for:
  - version,
  - model hash,
  - bind address,
  - API key set,
  - outbound rule present,
  - CSP header present,
  - encryption on,
  - log content check.
- **Exit:** packages install and uninstall cleanly on one clean Mac and one clean PC.

### Phase 2: Security testing (2 weeks). Each test passes or fails.
- [ ] **Network:** a port scan from another host on the same network finds nothing. Outbound attempts from the service account fail, shown in firewall or EDR logs.
- [ ] **API:** requests without the key are rejected. A test page on an external site cannot reach the API, including a DNS-rebinding attempt.
- [ ] **Exfiltration by rendering:** prompts that make the model emit markdown images, HTML `<img>`, and `<script>` pointing at an external test server cause **zero** requests to that server (checked in the server's access log).
- [ ] **Prompt injection:** documents containing hidden instructions (use AgentDojo-style payloads) produce no action beyond text. Record what the text says for training material.
- [ ] **Tamper:** changing one byte of the model file stops the service. A standard user cannot edit the model, config, API key file, or firewall rule.
- [ ] **Data at rest:** after the scheduled wipe, a search of the disk for a unique marker string from a test chat finds nothing in the browser profile, logs, or temp folders.
- [ ] **Drift:** manually break each control; the next compliance run reports it.
- [ ] **Independent review:** ask ISO (or an outside tester) to try to get a planted test "P3" record out of the machine.
- **Exit:** every test passes, and the findings are shared with ISO.

### Phase 3: Pilot (3–4 weeks, 2–3 people, synthetic or P1 data first)
- [ ] Use synthetic or de-identified stand-ins for the P3 tasks you expect (for example, coding open-ended survey responses or summarizing case notes).
- [ ] Measure quality against human coding. For qualitative coding, report inter-rater agreement between model and human (Krippendorff's α) rather than impressions.
- [ ] Measure speed on the slowest machine.
- [ ] Only after ISO confirms Phase 2: a small, supervised trial with real P3 data on one approved dataset.
- **Exit:** ISO sign-off for production use, with the conditions written down.

### Phase 4: Rollout and operations (ongoing)
- [ ] Training (30–45 min) with a signed attestation covering: P3 handling, never pasting output into unapproved tools, links and images in output, wrong answers, and reporting incidents.
- [ ] Data SOP: de-identify before use, minimum necessary data, where outputs may be stored, retention.
- [ ] Incident procedure: lost device, a suspected leak, or an output containing another person's data. Who to call (ISO) and within what time.
- [ ] Monthly: check llama.cpp advisories (<https://github.com/ggml-org/llama.cpp/security>), rebuild, re-run the Phase 2 tests automatically, push through MDM.
- [ ] Emergency path: a critical CVE in the parser or server gets patched within the timeline your ISO sets for its severity.
- [ ] Yearly: repeat the risk assessment and the independent test.

## 6. Repository work (what gets built here)

```
restricted/
  runtime/            pinned llama.cpp version + build script + SHA-256 manifest
  proxy/              CSP reverse proxy (single file) + tests
  packaging/mac/      LaunchDaemon plist, pf anchor, postinstall, .pkg build script
  packaging/windows/  service definition, firewall rule, .intunewin build script
  browser-policy/     Chrome/Edge managed policy JSON for the AVAL-R profile
  compliance/         daily check scripts (bash + PowerShell), output schema
  tests/              Phase 2 tests: network, API, exfil-render, tamper, at-rest
  docs/               IT runbook, ISO submission packet, user guide, SOP, training
```

I can start `restricted/` now. The parts that need UCLA details (code-signing identity, MDM specifics, EDR firewall policy) will be stubbed and clearly marked.

## 7. Open decisions

1. **Is a chat-only assistant useful enough?** If the P3 work you have in mind needs the model to go through many files, AVAL-R won't do it. The HCE path could, with an agent running inside the enclave.
2. **Can macOS block outbound traffic per account on your fleet?** If neither pf nor the EDR can do it, `--offline` plus loopback binding is the fallback. That is weaker, and ISO should know.
3. **Chat history:** wipe on close only (safest; users lose past chats), or keep for N days (convenient; more P3 at rest)?
4. **Model family:** same question as the standard stack (Qwen versus Gemma 4 versus gpt-oss) and whether any partner restricts model origin.
5. **Hardware floor:** P3 users should probably have 16 GB+ Apple Silicon or an NVIDIA GPU, or the tool will be too slow to be worth the approval effort.

## 8. Sources (checked 2026-09-23)

- Greshake, K., et al. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. *AISec '23*. https://arxiv.org/abs/2302.12173
- Debenedetti, E., et al. (2024). AgentDojo. *NeurIPS 2024 Datasets & Benchmarks*. https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html
- Hubinger, E., et al. (2024). Sleeper agents: Training deceptive LLMs that persist through safety training. https://arxiv.org/abs/2401.05566 (preprint)
- EchoLeak: The first real-world zero-click prompt injection exploit in a production LLM system (2025). https://arxiv.org/abs/2509.10540 (preprint; shows exfiltration through rendered content)
- llama.cpp server options (`--api-key`, `--offline`, `--host`, `--no-ui-mcp-proxy`): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- llama.cpp security advisories, including the GGUF heap overflows: https://github.com/ggml-org/llama.cpp/security
- NCC Group, Ollama DNS rebinding (CVE-2024-28224): https://www.nccgroup.com/research/technical-advisory-ollama-dns-rebinding-attack-cve-2024-28224/
- goose permission modes (no administrator lock documented): https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/managing-tools/goose-permissions.md
- UC Minimum Security Standard: https://security.ucop.edu/files/documents/policies/minimum-security-standard.pdf (I could not open it from this environment; the points above come from search summaries and the UCSF addendum)
- UCSF minimum security standards (EDR and managed-device language): https://it.ucsf.edu/standards-and-guidelines/ucsf-650-16-addendum-b-ucsf-minimum-security-standards-electronic-information
- UCLA High Compliance Environment: https://dts.ucla.edu/products-services/security/high-compliance-environment

## 9. The P4 path, in one paragraph

Run the same hardened `llama-server` inside UCLA's High Compliance Environment, with no internet access and access through the enclave's remote desktop, so data never leaves the enclave. The first question for OCISO is whether HCE can host a GPU inference server.
