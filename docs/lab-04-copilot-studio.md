# Lab 4 - Low-code intake + pro-code handoff

**Pillar:** Build · **Featured:** Copilot Studio, Copilot Studio VS Code extension / `pac`, `CopilotStudioClient` (M365 Agents SDK)

**Scenario:** a Copilot Studio intake agent collects onboarding details from the customer. The pro-code KYC agent then performs the regulated assessment.

## 1. Mock handoff

```powershell
$env:DEMO_MODE = 'mock'
.\.venv\Scripts\python src\copilot-studio-intake\intake_client.py "I want to open an account for CUST-1003"
```

The mock intake reply extracts the customer and hands off to `kyc_agent`.

## 2. Live

1. Create an "Account Intake" agent in Copilot Studio, or clone one with the VS Code extension (`clone-agent`).
2. Under **Settings → Security → Authentication**, configure the agent for Microsoft Entra authentication.
3. Create an app registration with the delegated permission **Power Platform API → CopilotStudio.Copilots.Invoke**, and allow public client flows.
4. Set the following in `.env`:

   ```text
   COPILOTSTUDIOAGENT__ENVIRONMENTID=...
   COPILOTSTUDIOAGENT__SCHEMANAME=...
   COPILOTSTUDIOAGENT__TENANTID=...
   COPILOTSTUDIOAGENT__AGENTAPPID=...
   ```

5. Run:

   ```powershell
   $env:DEMO_MODE = 'live'
   .\.venv\Scripts\python src\copilot-studio-intake\intake_client.py "Open a business account for Northwind Trading"
   ```

`CopilotClient.start_conversation()` and `ask_question()` stream activities from the low-code agent. The script then calls the governed pro-code agent.

See [README](../src/copilot-studio-intake/README.md).
