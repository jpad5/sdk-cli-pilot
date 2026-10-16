# Pro-code agents: Build · Manage · Govern

A hands-on workshop that builds an FSI **KYC/AML compliance agent**, using Microsoft's and GitHub's pro-code SDKs and CLIs end to end:

- **Build:** Microsoft Foundry SDK, MCP, M365 Agents SDK, M365 Agents Toolkit, Copilot Studio
- **Manage:** GitHub Copilot SDK, GitHub Actions, evals, OpenTelemetry
- **Govern:** Agent 365 SDK/CLI, Entra Agent ID, allow-lists, HITL, audit

> **Synthetic data only.** Every person, company and sanctions entry in `shared/mock` is fictional. This is a demo, not a compliance product.

Every lab runs **offline in `DEMO_MODE=mock`** (the default), with no Azure, M365 or Copilot sign-in required. Switch to `DEMO_MODE=live` to use real Foundry, Teams, Copilot Studio and Copilot CLI.

## Quick start (mock, ~2 minutes)

```powershell
.\scripts\setup.ps1            # venv + editable installs + npm install
.\scripts\run-mock-demo.ps1    # MCP server, 3 assessments, HITL approval, eval gate, audit summary
```

macOS and Linux: `./scripts/setup.sh && ./scripts/run-mock-demo.sh`

## SDKs and CLIs featured

| Pillar | SDK / CLI | Component |
| --- | --- | --- |
| Build | **Microsoft Foundry SDK** (`azure-ai-projects`), `azd`, `azd ai agent` | [src/foundry-kyc-agent](src/foundry-kyc-agent) |
| Build | **MCP Python SDK** (FastMCP) + Foundry `MCPTool` | [shared/mcp-sanctions](shared/mcp-sanctions) |
| Build | **Microsoft 365 Agents SDK** (Python) | [src/m365-host](src/m365-host) |
| Build | **Microsoft 365 Agents Toolkit CLI** (`atk`) | [src/atk-app](src/atk-app) |
| Build | **Copilot Studio** + `CopilotStudioClient` | [src/copilot-studio-intake](src/copilot-studio-intake) |
| Build / Manage | **GitHub Copilot SDK** (TypeScript) + `gh` | [src/agent-ops-copilot](src/agent-ops-copilot) |
| Manage | **GitHub Actions** (CI, eval gate, OIDC deploy), Foundry evals | [.github/workflows](.github/workflows) |
| Manage | **OpenTelemetry / Azure Monitor**, **Agent 365 observability SDK** | [shared/kyc_core](shared/kyc_core), [src/m365-host](src/m365-host) |
| Govern | **Agent 365 CLI** (`a365`), Entra Agent ID, agent registry | [Lab 8](docs/lab-08-agent365-identity.md) |
| Govern | `kyc_core` governance, managed identity + RBAC (Bicep) | [docs/GOVERNANCE.md](docs/GOVERNANCE.md), [infra](infra) |

## Workshop modules

| # | Module | Pillar |
| --- | --- | --- |
| 0 | [Setup and mode switch](docs/lab-00-setup.md) | - |
| 1 | [Build the KYC agent in Foundry](docs/lab-01-foundry-agent.md) | Build |
| 2 | [Add tools via MCP](docs/lab-02-mcp-tools.md) | Build |
| 3 | [Host in M365 / Teams](docs/lab-03-m365-teams.md) | Build |
| 4 | [Low-code intake + pro-code handoff](docs/lab-04-copilot-studio.md) | Build |
| 5 | [Dev-loop agent with the GitHub Copilot SDK](docs/lab-05-copilot-sdk.md) | Build / Manage |
| 6 | [Evaluate and gate](docs/lab-06-evals-gate.md) | Manage |
| 7 | [Observe and trace](docs/lab-07-observability.md) | Manage |
| 8 | [Identity, registry and publish (Agent 365)](docs/lab-08-agent365-identity.md) | Govern |
| 9 | [Govern and audit](docs/lab-09-govern-audit.md) | Govern |
| 10 | [Teardown](docs/lab-10-teardown.md) | - |

Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Interface contracts: [docs/CONTRACTS.md](docs/CONTRACTS.md)

## Live deployment

```powershell
azd auth login
azd up                                   # Foundry project + model, App Insights, Container App (M365 host), MI + RBAC
$env:DEMO_MODE = 'live'
.\.venv\Scripts\python -m kyc_agent deploy
.\scripts\setup-oidc.ps1                 # GitHub OIDC federated credential for the deploy workflow
gh variable set AZURE_DEPLOY_ENABLED --body true   # opt in to deploy-on-push (Deploy workflow skips Azure jobs otherwise)
```

## Repository layout

```text
shared/kyc_core        settings, models, governance (allow-list, audit, HITL), telemetry
shared/mcp-sanctions   FastMCP sanctions/PEP screening server
shared/mock            synthetic customers, sanctions list, canned LLM replies
src/foundry-kyc-agent  KYC agent (Foundry SDK) + AML evals
src/m365-host          M365 Agents SDK host (Teams), Agent 365 integration, Dockerfile
src/atk-app            ATK project (manifest, provision/deploy pipelines)
src/copilot-studio-intake  low-code intake → pro-code handoff
src/agent-ops-copilot  GitHub Copilot SDK ops agent (TypeScript)
infra/                 Bicep for azd
.github/               CI, eval gate, deploy, CODEOWNERS
scripts/               setup, mock demo, OIDC, teardown
```
