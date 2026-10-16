# Governance controls

The table maps each control to the SDK or CLI that implements it and to the place in this repository where you can see it working. Every control in the **Local** column also runs in `DEMO_MODE=mock`.

| # | Control | Implemented by | Where | Local |
| --- | --- | --- | --- | --- |
| 1 | **Tool allow-list** (least privilege per agent) | `kyc_core.governance.ToolPolicy`, `KYC_ALLOWED_TOOLS` | `shared/kyc_core/kyc_core/governance.py`, `kyc_agent/tools.py` (`@governed`) | Yes |
| 2 | **Append-only audit log** of tool calls, blocks, approvals and eval gates | `kyc_core.governance.AuditLog` (`.data/audit.jsonl`) | all tools, MCP server, M365 host, eval CLI | Yes |
| 3 | **Human-in-the-loop SAR approval** (no autonomous filing) | `require_approval()`, Adaptive Card approve/reject, `KYC_REVIEWER_IDS` | `kyc_agent/tools.py`, `src/m365-host/kyc_m365/handlers.py` | Yes |
| 4 | **Evaluation gate** before deploy (accuracy and safety) | custom AML grader + `python -m kyc_agent.evals` exit code | `src/foundry-kyc-agent/kyc_agent/evals`, `.github/workflows` | Yes |
| 5 | **Tracing / observability** | OpenTelemetry → App Insights; Agent 365 observability SDK | `kyc_core/telemetry.py`, `kyc_m365/a365_integration.py` | Console exporter |
| 6 | **Agent identity and registry** | Agent 365 CLI (`a365 setup blueprint`, `a365 publish`), Entra Agent ID | `src/m365-host/README.md`, Lab 8 | No (tenant) |
| 7 | **Managed identity, no keys** | user-assigned identity, `disableLocalAuth: true`, RBAC (Azure AI User, OpenAI User, AcrPull, KV Secrets User) | `infra/resources.bicep` | No (Azure) |
| 8 | **Content safety** | Foundry model deployment `raiPolicyName: Microsoft.DefaultV2` | `infra/resources.bicep` | No (Azure) |
| 9 | **Ops-agent permission gating** | Copilot SDK `onPermissionRequest` handler (blocks writes and shell, allows read-only tools) | `src/agent-ops-copilot/src/governance.ts` | Yes |
| 10 | **Change control** | CODEOWNERS, protected `production` environment with required reviewers, PR eval gate | `.github/` | GitHub |
| 11 | **Data protection and threat detection** (docs only) | Microsoft Purview (DSPM for AI, audit, retention), Defender for Cloud AI threat protection | links below | No |

## Try it

```powershell
# 1. Allow-list: remove draft_sar and watch the call get blocked and audited
$env:KYC_ALLOWED_TOOLS = 'lookup_customer,screen_name,risk_score'
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1007"
Remove-Item Env:KYC_ALLOWED_TOOLS

# 2. HITL: the SAR stays pending_approval until a named reviewer approves it
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1007"
.\.venv\Scripts\python -m kyc_agent chat "approve SAR-<id> as alice"

# 3. Audit trail
Get-Content .data\audit.jsonl -Tail 10
```

## Rules of the road

- Synthetic data only. `shared/mock` contains fictional people and entities. Never load real customer data into this workshop.
- `SAR_AUTO_APPROVE` must stay `false` outside unit tests. The Bicep pins it to `false`.
- Never commit `.env`, `.env.azd` or `.data/`; `.gitignore` excludes them.

## Further reading

- Microsoft Purview data security for AI: https://learn.microsoft.com/purview/ai-microsoft-purview
- Defender for Cloud AI threat protection: https://learn.microsoft.com/azure/defender-for-cloud/ai-threat-protection
- Microsoft Foundry guardrails and content filters: https://learn.microsoft.com/azure/ai-foundry/openai/concepts/content-filter
- Microsoft Entra Agent ID: https://learn.microsoft.com/entra/agent-id/
