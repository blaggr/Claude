# Maintainer checklist

## Monthly (and for any Ollama or goose security advisory)

1. **Check advisories**
   - Ollama: <https://github.com/ollama/ollama/security/advisories> and release notes
   - goose: <https://github.com/aaif-goose/goose/security/advisories> and release notes
   - Search the CVE database for "ollama" and "goose" since your last check.
   - If a fix raises the safe floor, bump `OLLAMA_MIN_VERSION` in `versions.conf`.
2. **Windows updater status (until resolved):** confirm whether a tagged Ollama release includes the CVE-2026-42248/42249 fix. Keep the tray app disabled regardless.
3. **Test on your own Mac and one Windows PC**
   - Run the installer from your working copy. All checks must PASS.
   - Record versions in `versions.conf` (`OLLAMA_TESTED_VERSION`, `GOOSE_TESTED_VERSION`).
   - Windows goose: download the release zip from <https://github.com/aaif-goose/goose/releases>, check it isn't a pre-release, run `Get-FileHash <zip> -Algorithm SHA256`, and put the URL and hash in `versions.conf`.
   - Pin models: after `ollama pull`, copy the 12-character ID from `ollama list` into `models.conf` for each tier you tested.
4. **Run the pilot task set** (PLAN §5) on any model change. Don't ship a model that scores worse on AVAL tasks without saying so.
5. **Release**
   - Update `STACK_VERSION` and `CHANGELOG.md`.
   - Commit, then tag: `git tag v1.x.y && git push --tags`.
   - Create a GitHub Release from the tag and attach a zip built with `git archive --format=zip -o aval-local-ai-v1.x.y.zip v1.x.y`. Publish its SHA-256 (`shasum -a 256 <zip>`) in the release notes. `git archive` keeps the executable bit on the `.command` files; GitHub's auto-generated "Source code" zip may not.
   - Email the team: link, SHA-256, one-line summary of what changed, "please run Install and send me the Verify output."

## Adding an extension (MCP server)

1. Read its source. Prefer servers from the official `modelcontextprotocol` org or well-known maintainers.
2. Pin an exact version in the command (e.g., `npx -y pkg@1.2.3`). Unpinned commands pull whatever is latest.
3. Add it to `config/goose/allowlist.yaml` and, if everyone should have it, to the `extensions:` block in `config/goose/config.yaml.template`.
4. Ask whether it adds a way for data to leave the machine (web fetch, email, cloud APIs). If yes, weigh that against PLAN §2.1.

## Changing models

Edit `models.conf`. Keep one family across tiers when you can. The installer pulls the new model and offers to remove old ones on the next run.
