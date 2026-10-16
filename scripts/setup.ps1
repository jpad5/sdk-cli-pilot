#Requires -Version 5.1
<#
.SYNOPSIS
  Workshop setup: Python venv + editable packages, npm install, .env, prerequisite report.
.PARAMETER Live
  Also install live extras (Foundry SDKs) and src/copilot-studio-intake requirements.
.PARAMETER CheckOnly
  Only print the prerequisite report; change nothing.
#>
[CmdletBinding()]
param(
    [switch]$Live,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }

function Test-Prerequisites {
    Write-Step 'Prerequisite check'
    $tools = [ordered]@{
        python  = 'Python 3.11+ (required)'
        node    = 'Node.js 20.19+ (required for agent-ops-copilot)'
        az      = 'Azure CLI (live labs)'
        azd     = 'Azure Developer CLI (deploy lab)'
        gh      = 'GitHub CLI (CI/CD + OIDC labs)'
        atk     = 'M365 Agents Toolkit CLI (Teams lab)'
        a365    = 'Agent 365 CLI (govern lab)'
        pac     = 'Power Platform CLI (Copilot Studio lab)'
        copilot = 'GitHub Copilot CLI (agent-ops lab)'
    }
    $missing = 0
    foreach ($name in $tools.Keys) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) {
            Write-Host ("  [ok]   {0,-8} {1}" -f $name, $cmd.Source) -ForegroundColor Green
        } else {
            $missing++
            Write-Warning ("{0,-8} not found - {1}" -f $name, $tools[$name])
        }
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($ver -and [version]$ver -lt [version]'3.11') { Write-Warning "python $ver found; 3.11+ required." }
    }
    Write-Host ("  {0} of {1} tools missing (mock mode only needs python + node)." -f $missing, $tools.Count)
}

Test-Prerequisites
if ($CheckOnly) { return }

$venvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Step 'Creating .venv'
    $basePy = Get-Command python -ErrorAction SilentlyContinue
    if (-not $basePy) { $basePy = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $basePy) { throw 'Python not found on PATH.' }
    & $basePy.Source -m venv (Join-Path $RepoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed.' }
}

function Invoke-Pip([string[]]$PipArgs) {
    & $venvPython -m pip @PipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip $($PipArgs -join ' ') failed." }
}

Write-Step 'Installing Python packages (editable)'
Invoke-Pip @('install', '--quiet', '--upgrade', 'pip')
$agentExtras = if ($Live) { 'dev,live' } else { 'dev' }
$packages = @(
    'shared/kyc_core[dev]',
    'shared/mcp-sanctions',
    "src/foundry-kyc-agent[$agentExtras]",
    'src/m365-host[test]'
)
foreach ($pkg in $packages) {
    Write-Host "  pip install -e $pkg"
    Invoke-Pip @('install', '--quiet', '-e', $pkg)
}
if ($Live) {
    Write-Host '  pip install -r src/copilot-studio-intake/requirements.txt'
    Invoke-Pip @('install', '--quiet', '-r', 'src/copilot-studio-intake/requirements.txt')
}

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Step 'npm install (src/agent-ops-copilot)'
    Push-Location (Join-Path $RepoRoot 'src/agent-ops-copilot')
    try {
        npm install --no-fund --no-audit
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
    } finally { Pop-Location }
} else {
    Write-Warning 'npm not found - skipping src/agent-ops-copilot install.'
}

$envFile = Join-Path $RepoRoot '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $RepoRoot '.env.example') $envFile
    Write-Step 'Created .env from .env.example (DEMO_MODE=mock)'
} else {
    Write-Step '.env already exists - left unchanged'
}

Write-Host ''
Write-Host 'Setup complete. Next: .\scripts\run-mock-demo.ps1' -ForegroundColor Green
