# Open questions for Rob

Answer these before the pilot. Q1 and Q2 can change the design.

**Q1. What data classification will people use this for?**
If any P3/P4 data or data under a partner DUA (CDPH, DCFS, QIC-WA sites) is in scope, we need a written position from the UCLA Information Security Office, and each DUA checked for clauses on software, storage location, or "AI tools". Until then the guide tells people **P1–P2 only**.

**Q2. Are the machines UCLA-managed (Jamf / Intune / BigFix), personal, or mixed?**
- Managed: IT may block unsigned scripts, Homebrew, or admin rights. The better path is to hand IT this repo and have them push it, and they also enforce FileVault/BitLocker.
- Personal: the scripts work, but we cannot enforce disk encryption or OS patching. Is that acceptable for the data in Q1?

**Q3. How many people, and what hardware?** (RAM, Apple Silicon or Intel, NVIDIA GPU on PCs.) Tiers in `models.conf` assume RAM is the constraint. Windows PCs without a GPU will be slow at tier 2 and up. If most machines are small, a single shared server (e.g., one Mac Studio on the lab network, behind auth and TLS) may give better quality than N weak laptops. It is also a larger security project.

**Q4. Is reproducibility across people required?** If yes, every machine runs the smallest-tier model (see PLAN §2.2).

**Q5. Model family.** The default is Qwen (Apache 2.0, strong tool calling, full size range). Some state and federal partners restrict PRC-origin AI products. Weights running offline cannot phone home, but the policy may not distinguish. The alternatives are Gemma 4 (Google, Apache 2.0) and gpt-oss (OpenAI, Apache 2.0). Do any of your contracts restrict this?

**Q6. Where should the release and allowlist be hosted?** goose fetches the extension allowlist from a URL at startup, and a private GitHub repo's raw URL needs a token. Options:
- (a) Make this repo public. It holds no secrets, only config. **Recommended.**
- (b) Keep it private and host `allowlist.yaml` plus release zips on GitHub Pages or a UCLA web server.
- (c) Skip the allowlist (weaker).

**Q7. Windows Ollama updater fix.** Before rollout, confirm a tagged Ollama release includes the CVE-2026-42248/42249 fix. Even after that, keep updates going through winget so versions stay pinned.

**Q8. Which extensions should the team have?** The default is the built-in `developer` extension only (files and shell, with approval). Candidates: `computercontroller` (browser and GUI automation, higher risk) and `memory`. Every addition widens what a prompt injection can reach.

**Q9. Who is the maintainer?** Someone must own the monthly check in `docs/MAINTAINER.md`. If that is you, budget about an hour a month plus advisories.
