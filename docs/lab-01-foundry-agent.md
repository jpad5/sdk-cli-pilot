# Lab 1 - Build the KYC agent in Microsoft Foundry

**Pillar:** Build · **Featured:** Foundry SDK (`azure-ai-projects` 2.x), `azd`, `azd ai agent`

## 1. Explore the agent (mock)

```powershell
$env:DEMO_MODE = 'mock'
foreach ($c in 1001..1008) { .\.venv\Scripts\python -m kyc_agent chat "Assess CUST-$c" }
```

| Customer | Expected | Why |
| --- | --- | --- |
| 1001 | APPROVE | clean |
| 1002 | EDD | politically exposed person |
| 1003 | REJECT | exact sanctions hit |
| 1004 | REJECT | sanctions alias match |
| 1005 | APPROVE | near-miss name (negative control) |
| 1006 | ESCALATE_SAR | risk 70 + suspicious activity |
| 1007 | ESCALATE_SAR | risk 90 |
| 1008 | EDD | adverse media |

Read [tools.py](../src/foundry-kyc-agent/kyc_agent/tools.py) for the risk rules and [workflow.py](../src/foundry-kyc-agent/kyc_agent/workflow.py) for the orchestration.

## 2. Provision Foundry with azd

```powershell
azd auth login
azd env new kyc-dev
azd env set AZURE_LOCATION eastus2
azd provision          # infra/main.bicep: Foundry account+project, gpt-4.1-mini, App Insights, Container Apps, MI + RBAC
```

The `postprovision` hook writes `.env.azd`. Copy `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT` into `.env`.

## 3. Deploy the agent version with the SDK

```powershell
$env:DEMO_MODE = 'live'
.\.venv\Scripts\python -m kyc_agent deploy
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1006"
```

Walk through [foundry_agent.py](../src/foundry-kyc-agent/kyc_agent/foundry_agent.py):

- `AIProjectClient(endpoint, DefaultAzureCredential())` authenticates without keys; the account has local auth disabled.
- `project.agents.create_version(agent_name=..., definition=PromptAgentDefinition(...))` creates a versioned agent, which you can inspect in the Foundry portal.
- `openai.responses.create(..., extra_body={"agent_reference": ...})` runs the agent. Each `function_call` is executed locally by the governed tools, and the result is sent back as `function_call_output`.

## 4. CLI-first alternative

```powershell
azd extension install azure.ai.agents
azd ai agent init
```

**Discussion:** SDK vs. CLI, and when to use prompt agents vs. hosted agents.
