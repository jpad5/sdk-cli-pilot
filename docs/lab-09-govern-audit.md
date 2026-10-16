# Lab 9 - Govern and audit

**Pillar:** Govern · **Featured:** `kyc_core` governance, HITL Adaptive Cards, Copilot SDK permission hooks, Purview / Defender (pointers)

Read [GOVERNANCE.md](GOVERNANCE.md) for the full control map.

## 1. Tool allow-list

```powershell
$env:KYC_ALLOWED_TOOLS = 'lookup_customer,screen_name,risk_score'
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1007"
# BLOCKED by governance policy: Tool 'draft_sar' is not in the governance allow-list...
Remove-Item Env:KYC_ALLOWED_TOOLS
```

## 2. Human-in-the-loop SAR

```powershell
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1007"          # SAR-XXXXXXXX pending_approval
.\.venv\Scripts\python -m kyc_agent chat "approve SAR-XXXXXXXX as alice"
```

In Teams (Lab 3), the approval is an Adaptive Card, and only Entra object IDs listed in `KYC_REVIEWER_IDS` can approve. A rejected or approved SAR is never overwritten.

## 3. Audit trail

```powershell
Get-Content .data\audit.jsonl | ConvertFrom-Json | Group-Object event | Select-Object Name, Count
```

The audit log records the following events:

- `tool_call`
- `tool_blocked`
- `mcp_tool_call`
- `sar_pending_approval`
- `sar_approved`
- `eval_gate`
- `permission_denied` (from the Copilot SDK ops agent)

## 4. Platform controls (discussion)

- **Content safety:** the model deployment uses `Microsoft.DefaultV2` guardrails.
- **Microsoft Purview:** DSPM for AI, audit, retention and DLP for agent interactions.
- **Defender for Cloud:** AI threat protection, including prompt-injection alerts.
- **GitHub:** CODEOWNERS on `src/foundry-kyc-agent/kyc_agent/tools.py`, plus a protected `production` environment.
