# Copilot Studio intake agent (low-code + pro-code)

This module shows how **Copilot Studio** (low-code) and **pro-code** agents work together:

```
Customer ──► Copilot Studio "Customer Intake" agent ──► (handoff) ──► Foundry KYC/AML agent
                 (topics, knowledge, guardrails)        CopilotStudioClient   (src/foundry-kyc-agent)
```

| Piece | Tooling |
|-------|---------|
| Author the intake agent as YAML in VS Code | Copilot Studio VS Code extension, or the Copilot Studio plugin in GitHub Copilot |
| Clone / push / pull the agent | Copilot Studio VS Code extension (Manage), or `pac copilot` (Power Platform CLI) |
| Call the agent from code | `microsoft-agents-copilotstudio-client` (M365 Agents SDK) – [intake_client.py](./intake_client.py) |

## 1. Run in mock mode (no tenant)

```powershell
$env:DEMO_MODE="mock"
.\.venv\Scripts\python src\copilot-studio-intake\intake_client.py "I want to open an account for CUST-1003"
```

## 2. Create and clone the intake agent (live)

> A Copilot Studio agent can't be created from scratch locally. You create it (even an empty one) in your environment, then clone it into this folder.

1. In <https://copilotstudio.microsoft.com>, create an agent named **Contoso Bank Intake** in your dev environment.
2. In VS Code, open this folder and clone the agent with the Copilot Studio extension (or ask GitHub Copilot: *"clone my Copilot Studio agent Contoso Bank Intake from environment &lt;env&gt;"*). This creates `agent.mcs.yml` plus `topics/`, `actions/`, `knowledge/`.
3. Ask GitHub Copilot (Copilot Studio plugin) to author the intake behaviour, for example:
   - *"Add a topic that collects the customer's legal name, date of birth, country, customer type and source of funds, then confirms back."*
   - *"Add the bank's public KYC policy page as a knowledge source."*
   - *"Disallow the agent from giving a credit or KYC decision; it must hand off to the compliance agent."*
4. Push the changes back to Copilot Studio and **publish**.
5. Under **Settings → Security → Authentication**, choose *Authenticate with Microsoft*. Then create an Entra app registration (public client, redirect `http://localhost`) with the delegated API permission **Power Platform API → CopilotStudio.Copilots.Invoke**.

## 3. Call it from pro-code (live)

Fill in `.env`:

```
DEMO_MODE=live
COPILOTSTUDIOAGENT__ENVIRONMENTID=<env id>
COPILOTSTUDIOAGENT__SCHEMANAME=<agent schema name, Settings → Advanced → Metadata>
COPILOTSTUDIOAGENT__TENANTID=<tenant id>
COPILOTSTUDIOAGENT__AGENTAPPID=<app registration client id>
```

```powershell
.\.venv\Scripts\pip install -r src\copilot-studio-intake\requirements.txt
.\.venv\Scripts\python src\copilot-studio-intake\intake_client.py "Open a business account for Northwind Trading"
```

The client streams the Copilot Studio replies, writes an `intake_handoff` audit record, and then calls the pro-code KYC agent.

## Governance notes
- Copilot Studio agents are governed by Power Platform DLP policies, environment routing and Managed Environments. Agent 365 / Entra Agent ID registers them in the same agent inventory as the pro-code agents.
- The handoff is audited (`.data/audit.jsonl`) and traced (`intake.*` spans).
