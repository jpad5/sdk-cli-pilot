# Lab 5 - Dev-loop agent with the GitHub Copilot SDK

**Pillar:** Build / Manage · **Featured:** GitHub Copilot SDK (`@github/copilot-sdk`, TypeScript), `gh` CLI

The **agent-ops** agent embeds the Copilot agent runtime in a Node app. It registers five custom tools that operate on the KYC agent, and a permission handler that decides which of those tools may run.

## 1. Mock (scripted, no Copilot CLI)

```powershell
cd src\agent-ops-copilot
npm install
npm test
$env:DEMO_MODE = 'mock'
npm run demo
```

## 2. Live (Copilot CLI in server mode)

```powershell
gh auth login
$env:DEMO_MODE = 'live'
npm run ops -- "Add an adverse-media screening tool, run evals, open a PR if they pass"
```

Code to walk through:

- [sdk.ts](../src/agent-ops-copilot/src/sdk.ts) contains `CopilotClient`, `createSession`, `defineTool` and streaming events.
- [tools.ts](../src/agent-ops-copilot/src/tools.ts) wraps the eval CLI, the audit log reader and `gh pr create`.
- [governance.ts](../src/agent-ops-copilot/src/governance.ts) contains `onPermissionRequest`. It allows the workshop's custom tools and exact read-only shell commands, denies everything else, and audits each denial.

**BYOK:** point the SDK at your Foundry model deployment instead of Copilot-hosted models. See the [README](../src/agent-ops-copilot/README.md).
