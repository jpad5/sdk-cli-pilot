# Microsoft 365 KYC/AML host

Python Microsoft 365 Agents SDK host. **Synthetic workshop data only; never use real customer data.**
The SDK activity endpoint is `http://127.0.0.1:3978/api/messages`; readiness is `/healthz`.

## Run from the repository root (PowerShell)

```powershell
.\.venv\Scripts\python -m pip install -e shared\kyc_core -e shared\mcp-sanctions -e src\foundry-kyc-agent -e 'src\m365-host[test]'
$env:DEMO_MODE='mock'
.\.venv\Scripts\python src\m365-host\app.py
```

In another terminal, `curl.exe http://127.0.0.1:3978/healthz`. Connect the Microsoft 365
Agents Playground (`agentsplayground`, formerly `teamsapptester`) to `/api/messages`.
Ask **Screen customer CUST-1003**. It returns text and a decision/risk/hits/SAR card.
Use Approve or Reject on a pending SAR. The reviewer name comes from the channel sender,
not `Action.Submit` data. Approve calls `kyc_core.governance.require_approval`; reject writes
`sar_rejected` without ever passing a named approver into that approval-only function.
No action files a regulatory report. All governance events append to `.data/audit.jsonl`.

Mock mode ignores Entra environment credentials, allows anonymous Playground traffic and
binds loopback by default. **Never expose anonymous mock hosting through a public tunnel.**
Ordinary Bot Framework activities return 201 and deliver replies through `serviceUrl`;
`deliveryMode: "expectReplies"` returns buffered replies inline for local HTTP testing.
No cloud endpoints are called in mock mode. Playground's local callback transport is still required.

```powershell
.\.venv\Scripts\python -m pytest src\m365-host\tests -q
```

Tests use a stub KycAgent and exercise the installed SDK with an aiohttp test client, including
text/card responses, welcome, approval, rejection, replay/cross-conversation rejection and audit.
The actual `kyc_agent` integration test runs when that concurrent component is installed.

## Live / Teams

Set `DEMO_MODE=live`, the Foundry settings from the root documentation, and:

```text
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHTYPE=ClientSecret
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID=<actual bot Entra client ID>
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID=<actual tenant ID>
CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET=<secret from a secure store>
KYC_REVIEWER_IDS=<comma-separated approved reviewer Entra object IDs>
```

Never commit secrets. Anonymous auth is rejected in live mode. JWT middleware authenticates incoming
channel requests; approvals additionally require a matching tenant and allow-listed reviewer ID.
Use the ATK package in `..\atk-app` and an authenticated HTTPS Container App/devtunnel endpoint.
The host stores pending SARs under `KYC_DATA_DIR/m365-approvals`, bound to tenant + conversation + SAR ID,
and rejects repeat decisions. For this workshop use **one process/replica** and a persistent volume.
The in-process lock/file store is not a production distributed approval store; use transactional,
access-controlled storage, retention policy and RBAC before scaling. SDK MemoryStorage is volatile.

## Container

**Build context must be the repository root**, not this directory:

```powershell
docker build -f src\m365-host\Dockerfile -t fsi-kyc-m365 .
docker run --rm -p 127.0.0.1:3978:3978 -e DEMO_MODE=mock fsi-kyc-m365
```

The image installs `shared/kyc_core`, `shared/mcp-sanctions`, `src/foundry-kyc-agent`, then this
host. Supply live secrets via the deployment's secret references, not Docker build arguments.
Container mode binds `0.0.0.0`; publish mock ports only on loopback. Mount `/app/.data` to retain audits/approvals.

## Optional Microsoft Agent 365 SDK integration

Agent 365 is distinct from the Microsoft 365 Agents channel SDK. These Agent 365 surfaces and
custom-engine Copilot discovery have preview/version-sensitive behavior. This workshop deliberately
keeps Agent 365 optional and does not claim automatic tenant registration or mail delivery.

```powershell
.\.venv\Scripts\python -m pip install -e 'src\m365-host[a365]'
```

`a365_integration.py` reexports `kyc_m365.a365_integration.A365Integration`:

- Live invocation and host-owned tool scopes use optional
  `microsoft_agents_a365.observability.core.InvokeAgentScope.start(Request, InvokeAgentScopeDetails, AgentDetails)`
  and `ExecuteToolScope.start(Request, ToolCallDetails, AgentDetails)`, verified against the official
  Python repository. Scope setup errors fall back to `kyc_core.telemetry.span`; business errors are not swallowed.
  SAR narratives, message text and user identities are not placed into these spans. Tools executed
  inside `kyc_agent` retain their own core telemetry; reported tool names are not fabricated as execution spans.
- Export/provider setup delegates to `kyc_core.telemetry.init_telemetry`. The core's preview `configure`
  call and both scope APIs were exercised with observability-core 1.0.0. Verify against current docs when upgrading.
  Tenant Agent 365 export additionally needs its approved app-only token resolver and exporter setup;
  installing the package alone does not configure export. OpenTelemetry/core remains the fallback.
- Inject an async `token_provider(scope)->token` to connect tenant-approved Agent ID authentication
  (for example the Agents SDK authentication sidecar/MSAL connection). No made-up runtime token API
  is used: `microsoft-agents-a365-runtime` currently supplies runtime utilities, not a generic token client.
  Identity acquisition fails closed when not configured. Do not log tokens or substitute a developer credential.
- Inject `tool_registrar(token)` for Work IQ MCP registration, and a separately authorized `mail_sender(sar_id)`
  callback. Framework-specific registration services are in the official
  `microsoft-agents-a365-tooling-extensions-*` packages; the base tooling package discovers server
  configuration and is not itself a universal tool runner. Verify the selected extension against current docs.
  Only an opaque SAR reference is sent. Explicitly add `notify_compliance` to `KYC_ALLOWED_TOOLS`
  before enabling mail. Agent identity consent, approved Work IQ endpoint and recipients are tenant-owned.
  Default host wiring intentionally sends no mail. Pass a configured integration to `KycHandler`/`create_app`.
- Mock identity, export, registration and mail hooks are logged no-ops and never call injected live providers.
  Notifications SDK (`microsoft-agents-a365-notifications`) is for inbound Agent 365 events; this
  host does not register its handlers or pretend the package sends outbound email.

## Agent 365 CLI: verified commands, not simulated provisioning

Verified against Microsoft Learn CLI reference and `microsoft/Agent365-devTools` source on the workshop
build date. **Not executed against a tenant.** The installed CLI release is authoritative; begin with
`a365 --help` and each command's `--help`. Roles/consent must be supplied by your tenant administrator.

```powershell
dotnet tool install -g Microsoft.Agents.A365.DevTools.Cli --prerelease
a365 --help
a365 setup requirements --help
a365 setup blueprint --help
a365 setup permissions --help
a365 publish --help
# Current agent-name flow (substitute your actual tenant ID / endpoint):
a365 setup requirements
a365 setup blueprint --agent-name fsi-kyc-aml --tenant-id $env:AZURE_TENANT_ID
a365 setup permissions bot --agent-name fsi-kyc-aml
a365 setup permissions mcp --agent-name fsi-kyc-aml
a365 publish --agent-name fsi-kyc-aml --tenant-id $env:AZURE_TENANT_ID
```

The current blueprint flow prompts for/registers an endpoint. To update an existing registration,
`a365 setup blueprint --agent-name fsi-kyc-aml --update-endpoint $env:BOT_MESSAGES_ENDPOINT` is present
in current source; use your complete HTTPS `/api/messages` URL and check `--help` for your release.
`a365 publish` uses/generates its own `manifest` directory (embedded templates in current CLI source),
updates manifest IDs and builds `manifest.zip`; **it does not itself upload to a registry**.
Inspect and customize the generated names, descriptions, icons and legal URLs before upload. Run
from a dedicated Agent 365 project directory or configure `deploymentProjectPath`; do not target
`src\atk-app` as though its ATK package were an Agent 365 blueprint package.
Follow its printed instructions to upload in Microsoft 365 admin center, approve access, and create/hire
an instance. Govern deployed agents through Microsoft 365 admin center Agent management/registry,
Entra agent identities/permissions, and applicable Purview policies; there is no invented `a365 govern` command.
A365 packaging is a separate flow: don't blindly replace the ATK manifest or use ATK's Teams app ID as a blueprint ID.

**Version discrepancy:** historical docs/sample tables list `a365 config init`, `a365 setup infrastructure`,
`a365 deploy`, `a365 deploy app`, and `a365 deploy mcp`. Current main command implementations/reference
no longer list `config` or `deploy`; the old `/cli/config` URL redirects to the command index.
Do not assume those commands exist. If your pinned release lists them in `--help`, its configuration file
is `a365.config.json`; `a365.config.example.json` here is an empty-ID starting point based on the official
sample, **not a complete runnable configuration**. Do not use A365 App Service deployment for this
workshop's azd-owned Container App. No `a365 config init`/`deploy` was run or claimed verified here.

### Sources

- [Agents Python SDK](https://github.com/microsoft/Agents-for-python), especially `test_samples/testing` and aiohttp hosting.
- [Agent 365 Python SDK](https://github.com/microsoft/Agent365-python) and [samples](https://github.com/microsoft/Agent365-Samples).
- [Agent 365 developer documentation](https://learn.microsoft.com/microsoft-agent-365/developer/).
- [CLI setup](https://learn.microsoft.com/microsoft-agent-365/developer/reference/cli/setup),
  [publish](https://learn.microsoft.com/microsoft-agent-365/developer/reference/cli/publish),
  [CLI source](https://github.com/microsoft/Agent365-devTools).



