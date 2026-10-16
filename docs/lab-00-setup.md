# Lab 0 - Setup and mode switch

**Goal:** get a working environment. Every later lab runs in `mock` mode with no cloud access. `live` mode is optional.

## Prerequisites

| Tool | Needed for | Install |
| --- | --- | --- |
| Python 3.11+ | agent, host, MCP, evals | https://www.python.org |
| Node.js 20+ | Copilot SDK ops agent, ATK CLI | https://nodejs.org |
| Git + GitHub CLI `gh` | Labs 5 and 6 | `winget install GitHub.cli` |
| Azure Developer CLI `azd` (live) | Labs 1 and 10 | `winget install Microsoft.Azd` |
| Azure CLI `az` (live) | auth, Bicep | `winget install Microsoft.AzureCLI` |
| M365 Agents Toolkit CLI `atk` (live) | Lab 3 | `npm i -g @microsoft/m365agentstoolkit-cli` |
| Agent 365 CLI `a365` (live) | Lab 8 | see the Agent 365 docs |
| Power Platform CLI `pac` (live, optional) | Lab 4 | `dotnet tool install -g Microsoft.PowerApps.CLI.Tool` |
| GitHub Copilot CLI (live) | Lab 5 | `npm i -g @github/copilot` |

## Install (PowerShell, repository root)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e shared\kyc_core -e shared\mcp-sanctions -e src\foundry-kyc-agent -e "src\m365-host[test]" pytest
Copy-Item .env.example .env
cd src\agent-ops-copilot; npm install; cd ..\..
```

Or run the bootstrap script: `.\scripts\setup.ps1`.

## Mode switch

```powershell
$env:DEMO_MODE = 'mock'   # default: offline, deterministic, synthetic data
$env:DEMO_MODE = 'live'   # Foundry, App Insights, Teams, Copilot Studio, Copilot CLI
```

All Python components read the mode through `kyc_core.config.settings()`. The TypeScript ops agent reads `process.env.DEMO_MODE`.

## Smoke test

```powershell
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1001"
# -> APPROVE ... [decision=approve tools=lookup_customer,screen_name,risk_score mode=mock]
```

## Live sign-in (optional)

```powershell
az login; azd auth login; gh auth login
atk auth login m365
```
