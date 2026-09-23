# Install on Windows

Takes 10–30 minutes, mostly downloading the model. No administrator rights needed on most machines.

**Before you start**
- Windows 10 (22H2) or Windows 11.
- At least 8 GB of memory (16 GB+ recommended) and 20 GB of free disk space. An NVIDIA GPU helps a lot; without one, responses will be slow.
- **Device encryption / BitLocker on.** If you're not sure, the Verify step will tell you. Ask IT to turn it on.
- **winget** (the "App Installer" app from the Microsoft Store). It's already on most Windows 11 PCs.

**Steps**
1. **Before unzipping:** right-click the downloaded zip → **Properties** → tick **Unblock** → OK. This stops Windows from blocking the scripts inside.
2. Unzip it and open the folder.
3. Double-click `Install-AVAL-AI.bat`. If SmartScreen appears: **More info** → **Run anyway**.
4. A window runs the install. If it asks about removing other models, answer **N** unless you know you don't need them.
5. At the end you'll see a list of PASS / WARN / FAIL lines. **Copy the whole block and send it to Rob.**
6. Open **goose (AVAL)** from the Start menu.

**Important:** do **not** open the "Ollama" app from the Start menu. Its built-in auto-updater has known security flaws (CVE-2026-42248/42249), so the AVAL setup runs Ollama in the background without it. If you open it by accident, right-click its tray icon → Quit, then run Verify.

**To check your setup later:** double-click `Verify-AVAL-AI.bat`.
