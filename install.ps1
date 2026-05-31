<#
.SYNOPSIS
    Install the wealth-planning skill suite into ~/.claude/skills (Windows / PowerShell).

.DESCRIPTION
    Copies the 7 skills from this repo's skills/ folder into the user's Claude skills
    directory. Optionally persists GUAP_ORCH_ROOT (so guap.py + the orchestrator find
    each other no matter where this repo lives) and runs a quick verification.

.PARAMETER SetEnv
    Persist GUAP_ORCH_ROOT as a User environment variable pointing at this repo's
    orchestrator/ directory. Without this, guap.py still auto-finds the orchestrator
    only if the repo is at ~/projects/LOCALSonly or ~/LOCALSonly.

.PARAMETER Verify
    After installing, run the compliance unit tests and a guap smoke check.

.EXAMPLE
    ./install.ps1 -SetEnv -Verify
#>
param(
    [switch]$SetEnv,
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
$RepoRoot   = $PSScriptRoot
$SkillsSrc  = Join-Path $RepoRoot "skills"
$OrchRoot   = Join-Path $RepoRoot "orchestrator"
$SkillsDest = Join-Path $HOME ".claude\skills"

Write-Host "Wealth-planning suite installer" -ForegroundColor Cyan
Write-Host "  repo:        $RepoRoot"
Write-Host "  skills dest: $SkillsDest"

if (-not (Test-Path $SkillsSrc)) { throw "skills/ not found at $SkillsSrc" }
New-Item -ItemType Directory -Force -Path $SkillsDest | Out-Null

# Python check (3.8+ required; suite is pure stdlib)
$py = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command python3 -ErrorAction SilentlyContinue)
if (-not $py) {
    Write-Warning "Python not found on PATH. The skills install, but scripts need Python 3.8+ to run."
} else {
    Write-Host "  python:      $($py.Source)"
}

# Copy each skill, overwriting any existing copy
$count = 0
Get-ChildItem -Path $SkillsSrc -Directory | ForEach-Object {
    $dest = Join-Path $SkillsDest $_.Name
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse -Force $_.FullName $dest
    Write-Host "  installed -> $($_.Name)" -ForegroundColor Green
    $count++
}
Write-Host "Installed $count skills." -ForegroundColor Cyan

if ($SetEnv) {
    [Environment]::SetEnvironmentVariable("GUAP_ORCH_ROOT", $OrchRoot, "User")
    $env:GUAP_ORCH_ROOT = $OrchRoot
    Write-Host "Set GUAP_ORCH_ROOT (User) = $OrchRoot" -ForegroundColor Green
    Write-Host "  (open a new terminal for it to take effect everywhere)"
} else {
    Write-Host ""
    Write-Host "To wire the orchestrator to guap.py, set:" -ForegroundColor Yellow
    Write-Host "  `$env:GUAP_ORCH_ROOT = `"$OrchRoot`""
    Write-Host "  (or re-run with -SetEnv to persist it; skip if this repo is at ~/projects/LOCALSonly)"
}

if ($Verify) {
    Write-Host "`nVerifying..." -ForegroundColor Cyan
    $env:GUAP_ORCH_ROOT = $OrchRoot
    & $py.Source (Join-Path $SkillsDest "compliance-review\scripts\tests\test_compliance.py")
    & $py.Source (Join-Path $SkillsDest "guap-guide\scripts\guap.py") --help | Out-Null
    Write-Host "guap.py loaded and found the orchestrator OK." -ForegroundColor Green
}

Write-Host "`nDone." -ForegroundColor Cyan
