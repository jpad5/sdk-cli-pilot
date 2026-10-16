# Lab 7 - Observe and trace

**Pillar:** Manage · **Featured:** OpenTelemetry, Azure Monitor / App Insights, Agent 365 observability SDK

## 1. Local spans (mock)

```powershell
$env:KYC_TELEMETRY_CONSOLE = 'true'
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1006"
```

Each governed tool emits a `tool.<name>` span, nested under the agent's `invoke_agent` span. See [telemetry.py](../shared/kyc_core/kyc_core/telemetry.py).

## 2. App Insights (live)

`azd provision` creates App Insights and connects it to the Foundry project. Set `APPLICATIONINSIGHTS_CONNECTION_STRING` (written to `.env.azd`). `kyc_core.telemetry.init_telemetry()` then calls `configure_azure_monitor()`.

To view the results:

- **Foundry portal:** Tracing.
- **App Insights:** Transaction search, filtered on `cloud_RoleName == "kyc-agent"`.

## 3. Agent 365 observability

```powershell
.\.venv\Scripts\python -m pip install -e "src\m365-host[a365]"
```

[a365_integration.py](../src/m365-host/kyc_m365/a365_integration.py) wraps each turn in Agent 365 `InvokeAgentScope` and `ExecuteToolScope`. The A365 observability packages are `microsoft-agents-a365-observability-core` and its extensions. When the packages or tenant config are missing, it falls back to plain OTel spans. Telemetry then appears against the agent's identity in the Microsoft 365 admin center agent registry.

## 4. Ask the ops agent

```powershell
cd src\agent-ops-copilot; npm run ops -- "Summarize the governance audit"
```
