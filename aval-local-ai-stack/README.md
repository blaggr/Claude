# AVAL Local AI Stack

A standard, locked-down setup for running AI models **on your own Mac or PC** at UCLA AVAL. Nothing you type leaves your computer.

- **Interface:** [goose Desktop](https://github.com/aaif-goose/goose), an open-source desktop assistant that can read and edit files in a folder you choose (similar to Claude Cowork).
- **Model runtime:** [Ollama](https://github.com/ollama/ollama), which runs the model locally on `127.0.0.1` only, with its cloud features turned off.
- **Models:** one family, sized to your computer's memory ([`models.conf`](models.conf)).

> **Status: draft, not yet piloted.** See [PLAN.md](PLAN.md) and [open questions](docs/QUESTIONS.md).
> **Data rule until told otherwise: P1–P2 data only.** No client-level, PHI, or DUA-restricted data.

## Team members: install or update

1. Download the latest release zip from the link Rob sends you, and check its SHA-256 if asked.
2. Unzip it.
3. Follow the page for your computer:
   - **Mac:** [docs/INSTALL-MAC.md](docs/INSTALL-MAC.md)
   - **Windows:** [docs/INSTALL-WINDOWS.md](docs/INSTALL-WINDOWS.md)
4. Read [docs/USING-GOOSE.md](docs/USING-GOOSE.md) (5 minutes).
5. Send the output of the **Verify** step back to Rob.

Updating uses the same steps with the newer zip.

## Maintainers

- [PLAN.md](PLAN.md): design, security model, rollout, sources
- [docs/SECURE-LAPTOP-PLAN.md](docs/SECURE-LAPTOP-PLAN.md): **AVAL-R**, the restricted profile for P3 data on UCLA-managed laptops (development plan)
- [docs/MAINTAINER.md](docs/MAINTAINER.md): monthly update and release checklist
- [versions.conf](versions.conf) and [models.conf](models.conf): what every machine gets
- [config/](config/): Ollama and goose settings pushed to every machine

## Repository layout

```
Install-AVAL-AI.command / .bat   double-click installers (Mac / Windows)
Verify-AVAL-AI.command / .bat    double-click security check
versions.conf                    pinned versions, minimum Ollama version, goose hash
models.conf                      model per RAM tier, pinned model IDs
config/ollama/server.json        local-only Ollama setting
config/goose/                    goose config template and extension allowlist
scripts/mac, scripts/windows     installer and verify logic
docs/                            team guides, maintainer checklist, open questions
```
