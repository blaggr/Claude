# AVAL Local AI Stack: security and configuration check for Windows.
# Prints PASS / WARN / FAIL. Paste the output to the maintainer.
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')

$os = (Get-CimInstance Win32_OperatingSystem).Caption
Write-Host "`nAVAL Local AI Stack check  |  $(Get-Date -Format 'yyyy-MM-dd HH:mm')  |  $env:COMPUTERNAME"
Write-Host "Stack $(Get-Conf 'STACK_VERSION')  |  $os  |  $(Get-RamGB) GB RAM"

# Ollama running and version
$ver = Get-OllamaVersion
$min = Get-Conf 'OLLAMA_MIN_VERSION'
$tested = Get-Conf 'OLLAMA_TESTED_VERSION'
if ($ver) {
    if (Test-VersionGE $ver $min) { Pass "Ollama $ver (minimum $min)" } else { Fail "Ollama $ver is below minimum $min" }
    if ($tested -and $ver -ne $tested) { Warn "Ollama $ver differs from the tested version $tested" }
} else { Fail "Ollama is not running on $OllamaAddr" }

# Bind address
$listen = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
if (-not $listen) { Fail 'Nothing is listening on port 11434' }
elseif ($listen | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }) {
    Fail "Ollama is reachable from the network: $(($listen | ForEach-Object { $_.LocalAddress }) -join ', ')"
} else { Pass 'Ollama listens on loopback only' }

# Cloud disabled
$serverJson = Join-Path $env:USERPROFILE '.ollama\server.json'
if ((Test-Path $serverJson) -and ((Get-Content $serverJson -Raw) -match '"disable_ollama_cloud"\s*:\s*true')) {
    Pass 'server.json disables Ollama cloud'
} else { Fail "$serverJson does not disable Ollama cloud" }
if ((Test-Path $OllamaLog) -and (Select-String -Path $OllamaLog -Pattern 'cloud disabled: true' -Quiet)) {
    Pass 'Ollama log confirms cloud disabled'
} else { Warn "Could not confirm 'cloud disabled: true' in $OllamaLog" }
if ([Environment]::GetEnvironmentVariable('OLLAMA_NO_CLOUD', 'User') -eq '1') { Pass 'OLLAMA_NO_CLOUD=1 set' } else { Fail 'OLLAMA_NO_CLOUD not set' }

# Tray app / auto-updater off
if (Get-Process -Name 'ollama app' -ErrorAction SilentlyContinue) {
    Fail "The Ollama tray app is running (its auto-updater is vulnerable). Quit it from the system tray."
} else { Pass 'Ollama tray app not running' }
if (Test-Path $StartupLnk) { Fail "Ollama tray app is set to start at login ($StartupLnk)" } else { Pass 'Ollama tray app not in Startup' }
$fallback = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\AVAL Ollama.lnk'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Pass 'AVAL Ollama logon task registered' }
elseif (Test-Path $fallback) { Pass 'AVAL Ollama starts at login (Startup shortcut)' }
else { Fail 'AVAL Ollama is not set to start at login' }

# Model
$pick = Get-ModelForMachine
if ($pick) {
    $row = & $OllamaExe list 2>$null | Select-Object -Skip 1 | Where-Object { ($_ -split '\s+')[0] -eq $pick.Model }
    if (-not $row) { Fail "Model $($pick.Model) (tier $($pick.Tier)) is not installed" }
    else {
        $id = ($row -split '\s+')[1]
        if ($pick.ExpectedId -eq '-') { Warn "Model $($pick.Model) present (ID $id); manifest ID not pinned yet" }
        elseif ($id -eq $pick.ExpectedId) { Pass "Model $($pick.Model) matches pinned ID $id" }
        else { Fail "Model $($pick.Model) ID $id does not match pinned $($pick.ExpectedId)" }
    }
}

# goose
if (Get-ChildItem $GooseDir -Recurse -Filter 'goose*.exe' -ErrorAction SilentlyContinue) { Pass 'goose Desktop installed' } else { Fail 'goose Desktop not installed' }
$cfg = Join-Path $GooseConfigDir 'config.yaml'
if (Test-Path $cfg) {
    $c = Get-Content $cfg -Raw
    if ($c -match '(?m)^GOOSE_MODE:\s*"?approve"?') { Pass 'goose asks before every tool call (approve mode)' } else { Fail 'goose is not in approve mode' }
    if ($c -match '(?m)^GOOSE_TELEMETRY_ENABLED:\s*false') { Pass 'goose telemetry off' } else { Fail 'goose telemetry not disabled' }
    if ($c -match '(?m)^active_provider:\s*ollama') { Pass 'goose uses local Ollama' } else { Fail 'goose provider is not Ollama' }
    if ($c -match '(?m)^GOOSE_ALLOWLIST:') { Pass 'goose extension allowlist set' } else { Warn 'goose extension allowlist not set' }
} else { Fail "goose config not found at $cfg" }

# OS controls (report only; these need IT or admin to change)
try {
    $bl = (New-Object -ComObject Shell.Application).NameSpace('C:').Self.ExtendedProperty('System.Volume.BitLockerProtection')
    if ($bl -eq 1 -or $bl -eq 6) { Pass 'BitLocker on for C:' }
    elseif ($bl -eq 3) { Warn 'BitLocker is still encrypting C:' } else { Fail "BitLocker is not on for C: (status code $bl). Ask IT to enable device encryption." }
} catch { Warn 'Could not read BitLocker status' }
$fw = Get-NetFirewallProfile -ErrorAction SilentlyContinue | Where-Object { -not $_.Enabled }
if ($fw) { Warn "Windows Firewall off for: $(($fw | ForEach-Object { $_.Name }) -join ', ')" } else { Pass 'Windows Firewall on' }

Write-Host "`nResult: $script:Failures failure(s), $script:Warnings warning(s)"
if ($script:Failures -gt 0) { exit 1 }
