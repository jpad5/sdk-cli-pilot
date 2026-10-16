# Architecture

```mermaid
flowchart LR
  subgraph Channels
    U[Analyst in Teams / M365 Copilot]
    CS[Copilot Studio intake agent<br/>low-code]
  end

  subgraph Build
    H[M365 host<br/>M365 Agents SDK - Python<br/>src/m365-host]
    A[KYC/AML agent<br/>Foundry SDK azure-ai-projects<br/>src/foundry-kyc-agent]
    M[Sanctions MCP server<br/>FastMCP<br/>shared/mcp-sanctions]
    IC[intake_client.py<br/>CopilotStudioClient]
  end

  subgraph Manage
    OPS[Agent-ops agent<br/>GitHub Copilot SDK - TS<br/>src/agent-ops-copilot]
    GH[GitHub Actions<br/>CI + eval gate + azd deploy]
    EV[AML evals<br/>custom grader]
    OT[OpenTelemetry / A365 observability<br/>App Insights]
  end

  subgraph Govern
    GOV[kyc_core governance<br/>allow-list - audit - HITL]
    A365[Agent 365 CLI/SDK<br/>blueprint - Entra Agent ID - registry]
    INF[azd + Bicep<br/>managed identity - RBAC - content safety]
  end

  U -->|Teams activity| H
  ATK[ATK CLI<br/>provision/deploy/publish] -.packages.-> U
  CS --> IC --> A
  H --> A
  A -->|function tools| GOV
  A -.MCP tool.-> M
  GOV --> M
  A --> OT
  H --> OT
  OPS -->|gh / evals / audit| GH
  GH --> EV --> A
  A365 -.registers.-> H
  INF -.provisions.-> A
  INF -.provisions.-> H
```

## Request flow (KYC assessment)

1. An analyst asks "Assess CUST-1007" in Teams. ATK packages and sideloads the app, and the M365 Agents SDK host receives the activity.
2. The host calls `kyc_agent`. In live mode this is a Foundry prompt agent driven through the Responses API; in mock mode it is a deterministic rule engine.
3. The agent calls governed tools in this order:
   - `lookup_customer`
   - `screen_name` (sanctions/PEP fuzzy match)
   - `risk_score`
   - optionally `draft_sar`

   Each call is checked against the allow-list, traced, and audited.
4. High risk combined with suspicious activity produces a SAR in `pending_approval`. The host sends an Adaptive Card, and only reviewers listed in `KYC_REVIEWER_IDS` can approve or reject it.
5. Spans go to App Insights (or the console in mock mode) through OpenTelemetry and Agent 365 observability.

## Mode switch

`DEMO_MODE=mock` (default) runs everything offline:

- mock LLM responses
- local synthetic data (`shared/mock`)
- console telemetry
- a scripted Copilot SDK demo

`DEMO_MODE=live` uses Foundry, App Insights, Teams, Copilot Studio and the Copilot CLI. See [CONTRACTS.md](CONTRACTS.md).

## Ports

| Component | Port |
| --- | --- |
| M365 host (`/api/messages`, `/healthz`) | 3978 |
| Sanctions MCP (`/mcp`, streamable HTTP) | 8765 |
