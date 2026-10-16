#Requires -Version 5.1
<#
.SYNOPSIS
  Configure GitHub Actions -> Azure OIDC (workload identity federation) for this repo.
.DESCRIPTION
  Creates an Entra app registration + service principal, adds federated credentials for
  refs/heads/main, pull_request and environment:production, assigns Azure roles, and
  stores AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_SUBSCRIPTION_ID as GitHub secrets.
  Supports -WhatIf / -Confirm.
.EXAMPLE
  .\scripts\setup-oidc.ps1 -Repo jpad5/sdk-cli-pilot -WhatIf
.EXAMPLE
  .\scripts\setup-oidc.ps1 -Repo jpad5/sdk-cli-pilot -ResourceGroup rg-kyc-prod
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [string]$Repo = 'jpad5/sdk-cli-pilot',
    [string]$AppName = 'gh-oidc-kyc-agent',
    [string]$SubscriptionId,
    # Scope role assignments to this RG; if omitted, the subscription is used (azd provision creates RGs).
    [string]$ResourceGroup,
    [string]$Environment = 'production',
    [switch]$SkipUserAccessAdministrator
)

$ErrorActionPreference = 'Stop'

foreach ($tool in 'az', 'gh') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool CLI not found on PATH." }
}

function Invoke-Az {
    $out = & az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed." }
    return $out
}

$account = Invoke-Az account show --output json | ConvertFrom-Json
if (-not $SubscriptionId) { $SubscriptionId = $account.id }
$tenantId = $account.tenantId
Write-Host "Tenant: $tenantId  Subscription: $SubscriptionId  Repo: $Repo"

$scope = "/subscriptions/$SubscriptionId"
if ($ResourceGroup) { $scope = "$scope/resourceGroups/$ResourceGroup" }

# 1. App registration (idempotent)
$appId = Invoke-Az ad app list --display-name $AppName --query '[0].appId' --output tsv
if (-not $appId) {
    if ($PSCmdlet.ShouldProcess($AppName, 'az ad app create')) {
        $appId = Invoke-Az ad app create --display-name $AppName --query appId --output tsv
    } else { $appId = '<new-app-id>' }
} else { Write-Host "App '$AppName' exists: $appId" }

# 2. Service principal
if ($appId -ne '<new-app-id>') {
    $spId = Invoke-Az ad sp list --filter "appId eq '$appId'" --query '[0].id' --output tsv
} else { $spId = $null }
if (-not $spId) {
    if ($PSCmdlet.ShouldProcess($AppName, 'az ad sp create')) {
        $spId = Invoke-Az ad sp create --id $appId --query id --output tsv
    } else { $spId = '<new-sp-object-id>' }
}

# 3. Federated credentials
$subjects = [ordered]@{
    'gh-main'         = "repo:${Repo}:ref:refs/heads/main"
    'gh-pull-request' = "repo:${Repo}:pull_request"
    "gh-env-$Environment" = "repo:${Repo}:environment:$Environment"
}
$existing = @()
if ($appId -ne '<new-app-id>') {
    $existing = @(Invoke-Az ad app federated-credential list --id $appId --query '[].subject' --output tsv)
}
foreach ($name in $subjects.Keys) {
    $subject = $subjects[$name]
    if ($existing -contains $subject) { Write-Host "Federated credential exists: $subject"; continue }
    if ($PSCmdlet.ShouldProcess($subject, 'az ad app federated-credential create')) {
        $params = @{
            name      = $name
            issuer    = 'https://token.actions.githubusercontent.com'
            subject   = $subject
            audiences = @('api://AzureADTokenExchange')
        } | ConvertTo-Json -Compress
        $paramFile = Join-Path $PSScriptRoot ".fic-$name.json"
        try {
            Set-Content -Path $paramFile -Value $params -Encoding utf8
            Invoke-Az ad app federated-credential create --id $appId --parameters "@$paramFile" --output none | Out-Null
        } finally { Remove-Item $paramFile -ErrorAction SilentlyContinue }
    }
}

# 4. Role assignments
# Contributor: azd provision/deploy. User Access Administrator: needed only because infra/main.bicep
# creates role assignments (managed identity -> Foundry/AI). Prefer an ABAC-conditioned UAA or
# have an admin pre-assign roles and pass -SkipUserAccessAdministrator for least privilege.
$roles = @('Contributor')
if (-not $SkipUserAccessAdministrator) { $roles += 'User Access Administrator' }
foreach ($role in $roles) {
    if ($PSCmdlet.ShouldProcess("$role @ $scope", 'az role assignment create')) {
        Invoke-Az role assignment create --assignee-object-id $spId --assignee-principal-type ServicePrincipal `
            --role $role --scope $scope --output none | Out-Null
    }
}

# 5. GitHub secrets
$secrets = [ordered]@{
    AZURE_CLIENT_ID       = $appId
    AZURE_TENANT_ID       = $tenantId
    AZURE_SUBSCRIPTION_ID = $SubscriptionId
}
foreach ($key in $secrets.Keys) {
    if ($PSCmdlet.ShouldProcess("$Repo secret $key", 'gh secret set')) {
        & gh secret set $key --repo $Repo --body $secrets[$key]
        if ($LASTEXITCODE -ne 0) { throw "gh secret set $key failed." }
    }
}

Write-Host ''
Write-Host 'Next steps:' -ForegroundColor Cyan
Write-Host "  - Create GitHub environment '$Environment' with required reviewers (governance approval)."
Write-Host '  - Set repo variables: AZURE_ENV_NAME, AZURE_LOCATION, FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT,'
Write-Host '    and optionally LIVE_EVALS=true, DEPLOY_TEAMS=true  (gh variable set NAME --body VALUE).'
Write-Host '  - Enable push-to-main deploys: gh variable set AZURE_DEPLOY_ENABLED --body true (manual dispatch always works).'
