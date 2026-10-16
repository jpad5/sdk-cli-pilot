# Lab 8 - Identity, registry and publish

**Pillar:** Govern · **Featured:** Agent 365 CLI (`a365`), Agent 365 SDK, Microsoft Entra Agent ID

Agent 365 is the control plane for enterprise agents. It gives each agent:

- an **Entra Agent ID** (agent blueprint → agent identity)
- registration in the **agent registry**
- governed permissions
- observability tied to that identity

## 1. Explore the CLI

```powershell
a365 --help
a365 setup requirements
```

## 2. Create the blueprint and permissions (live, tenant admin)

```powershell
Copy-Item src\m365-host\a365.config.example.json src\m365-host\a365.config.json   # edit tenant/subscription values
a365 setup blueprint --agent-name fsi-kyc-aml --tenant-id $env:AZURE_TENANT_ID
a365 setup permissions bot --agent-name fsi-kyc-aml
a365 setup permissions mcp --agent-name fsi-kyc-aml
a365 publish --agent-name fsi-kyc-aml --tenant-id $env:AZURE_TENANT_ID
```

Then check the result in the Microsoft 365 admin center under **Agents**:

- the agent's owner
- the agent's permissions
- the agent's lifecycle state (block / unblock)

## 3. Infrastructure identity

[resources.bicep](../infra/resources.bicep) gives the hosted agent a **user-assigned managed identity**. That identity has only these roles:

- Azure AI User
- Cognitive Services OpenAI User
- Key Vault Secrets User
- AcrPull

Foundry has `disableLocalAuth: true`, so the agent holds no API keys.

**Discussion:** Agent 365 identity (who the agent *is* in M365) vs. managed identity (how the workload authenticates to Azure).

Note that ATK and A365 packaging are separate flows. Do not reuse the ATK Teams app ID as the A365 blueprint ID. See the [m365-host README](../src/m365-host/README.md).
