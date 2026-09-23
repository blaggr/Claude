# AVAL Local AI Stack installer / updater for Windows 10/11.
# Safe to re-run: the same script installs, repairs, and updates.
# Run it through Install-AVAL-AI.bat (no admin rights needed).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$StackVersion  = Get-Conf 'STACK_VERSION'
$OllamaMin     = Get-Conf 'OLLAMA_MIN_VERSION'
$ContextTokens = Get-Conf 'CONTEXT_TOKENS'
$AllowlistUrl  = Get-Conf 'GOOSE_ALLOWLIST_URL'
$RecipeRepo    = Get-Conf 'GOOSE_RECIPE_REPO'
$GooseZipUrl   = Get-Conf 'GOOSE_WIN_ZIP_URL'
$GooseSha256   = Get-Conf 'GOOSE_WIN_SHA256'

Write-Host "AVAL Local AI Stack $StackVersion for Windows"

# 1. winget ------------------------------------------------------------------
Say 'Checking winget'
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Die 'winget is missing. Install "App Installer" from the Microsoft Store, then run this again.'
}

# 2. Ollama --------------------------------------------------------------------
Say 'Installing / updating Ollama'
$wingetArgs = @('--id', 'Ollama.Ollama', '--exact', '--silent', '--accept-package-agreements', '--accept-source-agreements')
$ErrorActionPreference = 'Continue'   # winget writes progress to stderr
$installed = (winget list --id Ollama.Ollama --exact --accept-source-agreements 2>&1 | Out-String) -match 'Ollama\.Ollama'
if ($installed) { winget upgrade @wingetArgs | Out-Host } else { winget install @wingetArgs | Out-Host }
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $OllamaExe)) { Die "ollama.exe not found at $OllamaExe after install." }

# 3. Remove the tray app and its auto-updater (CVE-2026-42248 / CVE-2026-42249).
Say 'Disabling the Ollama tray app and auto-updater'
Get-Process -Name 'ollama app', 'ollama' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
foreach ($lnk in @($StartupLnk, $StartMenuLnk)) {
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "  removed $lnk" }
}

# 4. Local-only settings ------------------------------------------------------
Say 'Applying local-only Ollama settings'
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', $OllamaAddr, 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
$ollamaHome = Join-Path $env:USERPROFILE '.ollama'
New-Item -ItemType Directory -Force -Path $ollamaHome | Out-Null
$serverJson = Join-Path $ollamaHome 'server.json'
if (Test-Path $serverJson) { Copy-Item $serverJson "$serverJson.bak-$(Get-Date -Format yyyyMMddHHmmss)" }
Copy-Item (Join-Path $RepoRoot 'config\ollama\server.json') $serverJson -Force

# 5. Run "ollama serve" at logon, hidden (instead of the tray app).
Say 'Registering the local Ollama logon task'
$avalDir = Split-Path $OllamaLog
New-Item -ItemType Directory -Force -Path $avalDir | Out-Null
$launcher = Join-Path $avalDir 'start-ollama.ps1'
@"
`$env:OLLAMA_HOST = '$OllamaAddr'
`$env:OLLAMA_NO_CLOUD = '1'
& "$OllamaExe" serve *>> "$OllamaLog"
"@ | Set-Content -Path $launcher -Encoding UTF8
$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
$FallbackLnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\AVAL Ollama.lnk'
try {
    $action   = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $psArgs
    $trigger  = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Set-Content -Path $OllamaLog -Value '' -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $TaskName
    if (Test-Path $FallbackLnk) { Remove-Item $FallbackLnk -Force }
} catch {
    # Some managed PCs block per-user logon tasks without admin rights.
    Write-Host "  Could not register a scheduled task ($($_.Exception.Message)). Using a Startup shortcut instead."
    $shell = New-Object -ComObject WScript.Shell
    $l = $shell.CreateShortcut($FallbackLnk)
    $l.TargetPath = 'powershell.exe'
    $l.Arguments = $psArgs
    $l.WindowStyle = 7
    $l.Save()
    Set-Content -Path $OllamaLog -Value '' -ErrorAction SilentlyContinue
    Start-Process powershell.exe -ArgumentList $psArgs -WindowStyle Hidden
}

Write-Host -NoNewline '  Waiting for Ollama to start'
$ver = $null
for ($i = 0; $i -lt 30 -and -not $ver; $i++) { Start-Sleep 1; Write-Host -NoNewline '.'; $ver = Get-OllamaVersion }
Write-Host ''
if (-not $ver) { Die "Ollama did not start. See $OllamaLog" }
if (-not (Test-VersionGE $ver $OllamaMin)) { Die "Ollama $ver is older than the required $OllamaMin." }
Write-Host "  Ollama $ver running on $OllamaAddr"

# 6. Model for this machine ----------------------------------------------------
$ram = Get-RamGB
Say "Choosing a model for this PC ($ram GB RAM)"
$pick = Get-ModelForMachine
if (-not $pick) { Die 'This PC has less RAM than the smallest tier in models.conf.' }
Write-Host "  Tier $($pick.Tier) -> $($pick.Model)"
$ErrorActionPreference = 'Continue'   # ollama writes progress to stderr
& $OllamaExe pull $pick.Model
if ($LASTEXITCODE -ne 0) { Die "Could not download $($pick.Model)." }
$ErrorActionPreference = 'Stop'

$others = & $OllamaExe list | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] } |
    Where-Object { $_ -and $_ -ne $pick.Model }
if ($others) {
    Write-Host '  Other models on this PC that are not in the AVAL manifest:'
    $others | ForEach-Object { Write-Host "    $_" }
    $ans = Read-Host '  Remove them to free disk space? [y/N]'
    if ($ans -match '^[Yy]') { $others | ForEach-Object { & $OllamaExe rm $_ } }
}

# 7. goose Desktop -------------------------------------------------------------
Say 'Installing / updating goose Desktop'
if (-not $GooseSha256 -or -not $GooseZipUrl) {
    Warn 'goose is not pinned yet (GOOSE_WIN_ZIP_URL / GOOSE_WIN_SHA256 blank in versions.conf). Skipping goose install. Ask the maintainer for the current release.'
} else {
    $zip = Join-Path $env:TEMP 'aval-goose.zip'
    Invoke-WebRequest -Uri $GooseZipUrl -OutFile $zip -UseBasicParsing
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    if ($hash -ne $GooseSha256.ToUpper()) {
        Remove-Item $zip -Force
        Die "goose download hash $hash does not match the pinned hash. Not installing. Tell the maintainer."
    }
    Get-Process -Name 'goose', 'Goose' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    if (Test-Path $GooseDir) { Remove-Item $GooseDir -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $GooseDir -Force
    Remove-Item $zip -Force
    $exe = Get-ChildItem $GooseDir -Recurse -Filter '*.exe' | Where-Object { $_.Name -match '^goose' } | Select-Object -First 1
    if (-not $exe) { Die "Could not find the goose executable in $GooseDir." }
    $sig = Get-AuthenticodeSignature $exe.FullName
    if ($sig.Status -ne 'Valid') { Warn "goose.exe Authenticode status: $($sig.Status) (hash was verified against the pinned value)." }
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\goose (AVAL).lnk'))
    $lnk.TargetPath = $exe.FullName
    $lnk.WorkingDirectory = $exe.DirectoryName
    $lnk.Save()
    Write-Host "  goose installed at $($exe.FullName)"
}

Say 'Writing team goose configuration'
New-Item -ItemType Directory -Force -Path $GooseConfigDir | Out-Null
$cfg = Join-Path $GooseConfigDir 'config.yaml'
if (Test-Path $cfg) { Copy-Item $cfg "$cfg.bak-$(Get-Date -Format yyyyMMddHHmmss)" }
$allowLine  = '# GOOSE_ALLOWLIST: (not set; see docs/QUESTIONS.md Q6)'
if ($AllowlistUrl) { $allowLine = "GOOSE_ALLOWLIST: `"$AllowlistUrl`"" }
$recipeLine = '# GOOSE_RECIPE_GITHUB_REPO: (not set)'
if ($RecipeRepo) { $recipeLine = "GOOSE_RECIPE_GITHUB_REPO: `"$RecipeRepo`"" }
$text = Get-Content (Join-Path $RepoRoot 'config\goose\config.yaml.template') -Raw
$text = $text.Replace('__MODEL__', $pick.Model)
$text = $text.Replace('__CONTEXT_TOKENS__', $ContextTokens)
$text = $text.Replace('__ALLOWLIST_LINE__', $allowLine)
$text = $text.Replace('__RECIPE_LINE__', $recipeLine)
# UTF-8 without BOM, so goose's YAML parser reads it cleanly.
[IO.File]::WriteAllText($cfg, $text, (New-Object System.Text.UTF8Encoding $false))
if ($AllowlistUrl) { [Environment]::SetEnvironmentVariable('GOOSE_ALLOWLIST', $AllowlistUrl, 'User') }

# 8. Verify --------------------------------------------------------------------
& (Join-Path $PSScriptRoot 'verify.ps1')
Write-Host "`nDone. Open 'goose (AVAL)' from the Start menu. Read docs\USING-GOOSE.md first."
Write-Host "Do NOT open the 'Ollama' app itself; its auto-updater is intentionally disabled."
