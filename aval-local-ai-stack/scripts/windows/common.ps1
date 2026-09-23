# Shared helpers for the AVAL Windows scripts. Dot-sourced, not run.
# Written for Windows PowerShell 5.1 (the version built into Windows 10/11).

$RepoRoot       = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$OllamaAddr     = '127.0.0.1:11434'
$OllamaDir      = Join-Path $env:LOCALAPPDATA 'Programs\Ollama'
$OllamaExe      = Join-Path $OllamaDir 'ollama.exe'
$OllamaLog      = Join-Path $env:LOCALAPPDATA 'AVAL\ollama.log'
$TaskName       = 'AVAL Ollama (local only)'
$StartupLnk     = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk'
$StartMenuLnk   = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Ollama.lnk'
$GooseDir       = Join-Path $env:LOCALAPPDATA 'Programs\AVAL-goose'
$GooseConfigDir = Join-Path $env:APPDATA 'Block\goose\config'

$script:Failures = 0
$script:Warnings = 0
function Say($m)  { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Pass($m) { Write-Host "  PASS  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  WARN  $m" -ForegroundColor Yellow; $script:Warnings++ }
function Fail($m) { Write-Host "  FAIL  $m" -ForegroundColor Red; $script:Failures++ }
function Die($m)  { Write-Host "`nERROR: $m" -ForegroundColor Red; exit 1 }

function Get-Conf([string]$Key) {
    $line = Get-Content (Join-Path $RepoRoot 'versions.conf') |
        Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if ($line) { return $line.Substring($Key.Length + 1).Trim() }
    return ''
}

function Test-VersionGE([string]$A, [string]$B) {
    try { return ([version]$A) -ge ([version]$B) } catch { return $false }
}

function Get-RamGB {
    $bytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    # Windows reports slightly less than installed RAM; round to the nearest GB.
    return [int][math]::Round($bytes / 1GB)
}

# Returns @{Tier; Model; ExpectedId} for this machine, or $null.
function Get-ModelForMachine {
    $ram = Get-RamGB
    $best = $null
    foreach ($line in Get-Content (Join-Path $RepoRoot 'models.conf')) {
        if ($line -match '^\s*#' -or $line.Trim() -eq '') { continue }
        $f = $line.Trim() -split '\s+'
        if ($f.Count -lt 4) { continue }
        $min = [int]$f[1]
        if ($min -le $ram -and ($best -eq $null -or $min -ge $best.Min)) {
            $best = @{ Tier = $f[0]; Min = $min; Model = $f[2]; ExpectedId = $f[3] }
        }
    }
    return $best
}

function Get-OllamaVersion {
    try {
        $r = Invoke-RestMethod -Uri "http://$OllamaAddr/api/version" -TimeoutSec 2
        return $r.version
    } catch { return $null }
}
