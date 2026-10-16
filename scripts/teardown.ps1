#Requires -Version 5.1
<#
.SYNOPSIS
  Tear down workshop Azure resources (azd down --purge --force), optionally deleting the OIDC app.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [switch]$DeleteOidcApp,
    [string]$AppName = 'gh-oidc-kyc-agent'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Get-Command azd -ErrorAction SilentlyContinue)) { throw 'azd not found on PATH.' }

if ($PSCmdlet.ShouldProcess('azd environment resources', 'azd down --purge --force')) {
    azd down --purge --force
    if ($LASTEXITCODE -ne 0) { throw "azd down failed ($LASTEXITCODE)." }
}

if ($DeleteOidcApp) {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'az not found on PATH.' }
    $appId = az ad app list --display-name $AppName --query '[0].appId' --output tsv
    if (-not $appId) {
        Write-Warning "App registration '$AppName' not found."
    } elseif ($PSCmdlet.ShouldProcess("$AppName ($appId)", 'az ad app delete')) {
        az ad app delete --id $appId
        if ($LASTEXITCODE -ne 0) { throw 'az ad app delete failed.' }
        Write-Host "Deleted app registration $AppName ($appId). Remove AZURE_* GitHub secrets if no longer needed."
    }
}
