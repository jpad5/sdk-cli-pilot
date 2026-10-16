# Agent Ops Copilot

**Build → Manage → Govern agents with SDKs & CLIs** — the development assistant for the synthetic FSI KYC/AML workshop.

## What the SDK is

The [GitHub Copilot SDK](https://github.com/github/copilot-sdk) embeds the agent runtime behind Copilot CLI in an application. Your app supplies tools, policy, session configuration, and UI; the runtime handles model reasoning and tool invocation. This is a **developer agent**, distinct from the Python **KYC compliance agent** it evaluates and scaffolds.

This component pins **`@github/copilot-sdk` 1.0.22** and its lockfile. Its package declares Copilot runtime **1.0.98**. Current releases bundle an optional platform runtime; a separate global CLI is not normally required. Follow the SDK's installation guidance if your platform package is unavailable. Older examples using `cwd` or older permission shapes do not match this release.

## Run locally (PowerShell)

Requires Node **20.19+ in the 20.x line, or 22.12+**, npm, and the repository's Python `.venv` for evaluations. From this folder:

```powershell
npm install
npm run typecheck
npm run build
npm test
$env:DEMO_MODE = 'mock'
npm run demo
npm run ops -- "Add an adverse-media screening tool, run evals, open a PR if they pass"
```

`mock` is the default. No Copilot client is created, no Copilot runtime starts, and no GitHub/cloud calls are made by this component. Any prompt runs the same deterministic demonstration plan, **not** natural-language interpretation. Mock still executes the local evaluator with `--mode mock`; missing `.venv` or evaluator is reported as unavailable and PR creation is skipped. Repeat the demo after installing the Python component and shared packages using the root setup instructions.

Environment variables must be exported in the shell; this component does **not** automatically load the repository `.env`. `DEMO_MODE` values other than `mock` and `live` are rejected. Paths resolve from the entrypoint, not the shell's current directory. The compiled entrypoint also works: `node dist\src\cli.js --demo`.

### Live Copilot-backed mode

Authenticate Copilot using the [current Copilot SDK authentication instructions](https://github.com/github/copilot-sdk/blob/main/docs/auth/index.md), or configure BYOK below. Live operations may incur model charges and create a real PR.

```powershell
$env:DEMO_MODE = 'live'
# Optional: select a model available to your account.
$env:COPILOT_MODEL = '<available-model-id>'
npm run ops -- "Summarize the governance audit and read the current evaluation results"
```

Before asking for a live PR, create and push a feature branch yourself, with reviewed changes committed. The assistant intentionally cannot commit or push. `gh` must be installed and authenticated with permission to create PRs. No `gh` authentication is needed in mock mode.

## Tools and artifact contracts

| Tool | Behavior |
| --- | --- |
| `run_evals` | Spawns repo `.venv\Scripts\python.exe` (POSIX: `.venv/bin/python`) with `-m kyc_agent.evals --mode mock\|live --threshold 0.8`, repository cwd, and Python package paths. Returns the JSON summary from `.data\eval-results.json` plus status/exit code. Timeout: 120 seconds. |
| `read_eval_results` | Reads the summary; missing/invalid JSON returns an explicit unavailable status. Reading alone does not authorize a PR. |
| `scaffold_tool` | Validates a snake_case name; emits a Python function candidate and pytest test file. Live destinations: `src\foundry-kyc-agent\kyc_agent\<name>.py` and `src\foundry-kyc-agent\tests\test_<name>.py`. Existing files are never overwritten. Mock destinations mirror these paths beneath `.data\preview\`; identical previews can be rerun. Prints a unified addition diff. |
| `open_pr` | Requires a successful, fresh eval run **in the current process**, after any scaffolding; checks the results file digest has not changed. Calls `gh pr create --title ... --body ...` with argument arrays and no shell. Mock prints the equivalent command without invoking `gh`. |
| `audit_summary` | Summarizes `.data\audit.jsonl` event counts, denials, and malformed lines. Does not return raw events or customer data. |

**A stub is not a completed adverse-media service.** It deliberately returns `not_implemented` and `requires_review: true`, and never clears a customer. Review and implement its data source, apply the compliance agent's `ToolPolicy`/audit wrapper, register it as a Foundry function tool, and add meaningful screening evaluations before real use. Mock evaluations exercise the **existing agent**, not code in `.data\preview`. Passing baseline evals are not proof that the candidate tool is implemented, registered, or compliant.

The eval CLI's nonzero exit is authoritative for failure. A successful exit must also produce a fresh, parseable results artifact; stale results cannot open a PR. Tool summaries are intentionally schema-agnostic to preserve the shared contract. Eval failure skips the PR; missing dependencies do not fabricate successful results. The scripted mock demo itself exits normally after explaining the skip.

Operations append metadata-only JSONL entries to the shared audit path, including denials, scaffolding, eval completion, and live PR attempts. Do not use real customer data in this workshop.

## Governance of the development assistant

Defense in depth:

1. `availableTools` exposes only the five custom tools plus built-in `powershell`/`bash`.
2. `hooks.onPreToolUse` denies all other tools, including built-in writes, network, delegation, and arbitrary execution. Allowed calls still go through runtime permissions; the hook does not auto-approve and bypass managed policy.
3. `onPermissionRequest` permits only `kind: "custom-tool"` with the exact five names, or `kind: "shell"` with the exact commands below. Denies unknown kinds, managed-human-approval requests, redirects, network URLs, and sandbox bypasses. Denials are audited before returning `denied-by-permission-request-hook`.
4. Custom tools independently validate input and enforce the eval-to-PR gate. No arbitrary executable, command, path, Python snippet, or PR body is accepted from the model.

Read-only shell command allow-list (case-sensitive, no extra switches/operators):

```text
git status --short
git --no-pager status --short
git diff --stat
git --no-pager diff --stat
pwd
Get-Location
```

This is a workshop application policy, **not an OS security sandbox**. Run in a trusted synthetic-data checkout. SDK permission callbacks do not sandbox host custom-tool code. Repo-local Git configuration may run hooks/helpers, and the evaluator executes repository Python code. Treat local code/configuration as trusted and keep enterprise sandbox/content-exclusion/managed policies enabled. The assistant does not auto-approve managed requests: unattended requests requiring human approval fail closed.

## BYOK with Microsoft Foundry / Azure OpenAI

BYOK uses your model endpoint and billing, bypassing Copilot API authentication for the session. It still uses the Copilot runtime and the same custom tools/policy. Configure an existing deployment and export secrets locally; never commit keys.

For an OpenAI-compatible Foundry/Azure OpenAI **v1** inference endpoint:

```powershell
$env:DEMO_MODE = 'live'
$env:COPILOT_MODEL = '<your-deployment-name>'
$env:FOUNDRY_MODEL_URL = 'https://<resource>.openai.azure.com/openai/v1/'
$env:FOUNDRY_API_KEY = '<set-securely-in-your-shell>'
$env:COPILOT_PROVIDER_TYPE = 'openai'
$env:COPILOT_WIRE_API = 'completions'
npm run ops -- "Summarize the governance audit"
```

Choose `responses` instead of `completions` only when your deployment supports the Responses API. `COPILOT_MODEL` is the deployment name, not the Foundry project URL. The endpoint must be an HTTPS inference endpoint without embedded credentials, query, or fragment.

For a **native Azure** endpoint, set `COPILOT_PROVIDER_TYPE=azure`, `FOUNDRY_MODEL_URL=https://<resource>.openai.azure.com/`, and, if using a versioned deployment route, `AZURE_OPENAI_API_VERSION=<supported-api-version>`. Omit the version for the SDK's versionless v1 behavior. Provider credentials must be supplied alongside `COPILOT_MODEL`; invalid provider/wire settings fail before session creation. Remove `FOUNDRY_MODEL_URL` to return to Copilot-backed authentication. The library also supports `bearerToken` and `bearerTokenProvider` for advanced authentication; this workshop CLI intentionally exposes only the API-key path.

References: [SDK BYOK guide](https://github.com/github/copilot-sdk/blob/main/docs/auth/byok.md), [Microsoft Azure OpenAI v1 lifecycle and endpoint examples](https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle).

## Verified API surface

Verified against the upstream [Node SDK docs](https://github.com/github/copilot-sdk/tree/main/nodejs) and installed package declarations (`node_modules\@github\copilot-sdk\dist\*.d.ts`):

- `new CopilotClient({ workingDirectory })`; `client.createSession(config)`; `client.stop()`.
- `defineTool(name, { parameters: JSONSchema, handler })`; tools return JSON-serializable objects.
- `session.sendAndWait({ prompt }, timeoutMs)`; `session.on(event => ...)`; `assistant.message_delta.data.deltaContent`; `session.disconnect()`.
- `systemMessage: { mode: "append", content }`, `availableTools`, `hooks.onPreToolUse`, `onPermissionRequest`.
- Discriminated permission requests: `custom-tool.toolName`, `shell.fullCommandText`, `hasWriteFileRedirection`, `possibleUrls`, and managed/sandbox escalation flags. Current deny results are not the old illustrative `deny` string.
- `provider: { type: "openai" | "azure", baseUrl, apiKey, wireApi, azure?: { apiVersion } }`.

No live model call or real GitHub PR is needed for tests. Tests cover both tool paths with an injected runner, failure/staleness/tampering gates, preview-only scaffolding, subprocess errors, audit aggregation, SDK tool definitions, BYOK validation, and deny-by-default permissions. Mock demo can be retried once the Python agent exists.
