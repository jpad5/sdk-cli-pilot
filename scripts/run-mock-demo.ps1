#Requires -Version 5.1
<#
.SYNOPSIS
  End-to-end mock demo: MCP sanctions server, three onboarding chats, SAR approval (HITL),
  mock evals and an audit summary. No cloud resources required.
#>
[CmdletBinding()]
param(
    [int]$Port = 8765,
    [int]$StartupTimeoutSeconds = 60,
    [string]$Approver = 'Workshop Reviewer'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$env:DEMO_MODE = 'mock'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:MCP_SANCTIONS_URL = "http://127.0.0.1:$Port/mcp"

$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Missing $python - run .\scripts\setup.ps1 first." }

$defaultDataDir = Join-Path $RepoRoot '.data\demo-run'
$dataDir = if ($env:KYC_DATA_DIR) { $env:KYC_DATA_DIR } else { $defaultDataDir }
# Fresh state each run (only for the script's own folder) so SAR statuses and audit counts are repeatable.
if ($dataDir -eq $defaultDataDir -and (Test-Path $dataDir)) { Remove-Item -Recurse -Force $dataDir }
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$env:KYC_DATA_DIR = $dataDir

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }

function Test-Port([int]$P) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', $P, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(500) -and $client.Connected) { $client.EndConnect($iar); return $true }
        return $false
    } catch { return $false } finally { $client.Close() }
}

function Stop-ProcessTree([int]$ProcessId) {
    # venv python.exe on Windows is a launcher that spawns the real interpreter as a child.
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ProcessTree -ProcessId $_.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Invoke-Agent([string]$Message) {
    Write-Host "you> $Message" -ForegroundColor Yellow
    $ErrorActionPreference = 'Continue'  # don't let native stderr become terminating errors
    $out = & $python -m kyc_agent chat $Message 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { $out | Write-Host; throw "kyc_agent chat failed ($LASTEXITCODE): $Message" }
    $out | Write-Host
    return ($out -join "`n")
}

if (Test-Port $Port) { throw "Port $Port is already in use - stop the existing MCP server first." }

$server = $null
$serverLog = Join-Path $dataDir 'mcp-server.log'
$serverErr = Join-Path $dataDir 'mcp-server.err.log'
try {
    Write-Step "Starting sanctions MCP server on http://127.0.0.1:$Port/mcp"
    $server = Start-Process -FilePath $python -ArgumentList '-m', 'kyc_sanctions.server', '--http' `
        -WorkingDirectory $RepoRoot -NoNewWindow -PassThru `
        -RedirectStandardOutput $serverLog -RedirectStandardError $serverErr
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while (-not (Test-Port $Port)) {
        if ($server.HasExited) { Get-Content $serverErr -ErrorAction SilentlyContinue | Write-Host; throw 'MCP server exited during startup.' }
        if ((Get-Date) -gt $deadline) { throw "MCP server did not open port $Port within $StartupTimeoutSeconds s." }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "  MCP server up (PID $($server.Id))" -ForegroundColor Green

    Write-Step 'Onboarding chats'
    $null = Invoke-Agent 'onboard CUST-1001'
    $null = Invoke-Agent 'onboard CUST-1003'
    $sarReply = Invoke-Agent 'onboard CUST-1007'

    Write-Step 'Human-in-the-loop SAR approval'
    $match = [regex]::Match($sarReply, 'SAR-[A-Za-z0-9]+')
    if (-not $match.Success) { throw 'No SAR id found in CUST-1007 output.' }
    $approval = Invoke-Agent "approve $($match.Value) as $Approver"
    if ($approval -notmatch 'approved') { throw "SAR approval did not succeed: $approval" }

    Write-Step 'Mock evals'
    & $python -m kyc_agent.evals --mode mock --threshold 0.8
    if ($LASTEXITCODE -ne 0) { throw "Mock evals below threshold (exit $LASTEXITCODE)." }

    Write-Step 'Audit summary'
    $auditFile = Join-Path $dataDir 'audit.jsonl'
    if (Test-Path $auditFile) {
        $events = Get-Content $auditFile | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json }
        $events | Group-Object -Property event | Sort-Object Count -Descending |
            Format-Table @{ n = 'Event'; e = { $_.Name } }, Count -AutoSize | Out-String | Write-Host
        Write-Host "  $(@($events).Count) audit events in $auditFile"
    } else {
        Write-Warning "No audit log at $auditFile"
    }
    Write-Host "`nMock demo completed successfully." -ForegroundColor Green
}
finally {
    if ($server) {
        Write-Step "Stopping MCP server (PID $($server.Id))"
        Stop-ProcessTree -ProcessId $server.Id
    }
}
