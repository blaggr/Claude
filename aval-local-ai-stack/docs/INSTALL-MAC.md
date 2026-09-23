# Install on a Mac

Takes 10–30 minutes, mostly downloading the model. You need your Mac login password once, for Homebrew.

**Before you start**
- macOS 14 or newer. Apple Silicon (M1 or later) strongly recommended.
- At least 8 GB of memory and 20 GB of free disk space.
- **FileVault on:** System Settings → Privacy & Security → FileVault.

**Steps**
1. If you don't have Homebrew: download the `.pkg` from <https://github.com/Homebrew/brew/releases/latest>, open it, and follow the prompts. (The installer will tell you if you need this.)
2. Unzip the AVAL release. Open the folder.
3. **Right-click** `Install-AVAL-AI.command` → **Open** → **Open**. Right-click is needed the first time because the script isn't signed by Apple.
   - If macOS still blocks it: System Settings → Privacy & Security → scroll down → **Open Anyway**.
4. A Terminal window runs the install. If it asks about removing other models, answer **N** unless you know you don't need them.
5. At the end you'll see a list of PASS / WARN / FAIL lines. **Copy the whole block and send it to Rob.**
6. Open **Goose** from Applications.

**If you already had the Ollama app** (`/Applications/Ollama.app`): quit it and move it to the Trash. Your models are kept. The AVAL setup runs Ollama in the background without the menu-bar app, so updates go through us.

**To check your setup later:** double-click `Verify-AVAL-AI.command` in the same way.
