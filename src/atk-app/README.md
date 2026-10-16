# Agents Toolkit: KYC/AML custom engine agent

This is an **app package/registration project**, not a declarative agent and not a second runtime.
The Python channel host lives in `..\m365-host`; azd owns its Container App deployment.
Mock mode can run locally without any tenant, Entra registration, ATK provisioning or cloud services.
Use the Agents Playground first; see the host README. **Do not publicly tunnel anonymous mock mode.**

## Configure live registration

Fill `env\.env.dev` with real values (no credentials belong in this file):

- `BOT_ID`: the host's Entra application/client ID, not the Teams app ID, Foundry agent ID or A365 identity ID.
- `BOT_ENDPOINT`: HTTPS **origin**, no trailing slash, from the azd-deployed host or an authenticated live-mode
  devtunnel (`https://<your-tunnel-host>`). The lifecycle registers `${BOT_ENDPOINT}/api/messages`.
- `BOT_DOMAIN`: hostname only from that endpoint.
- `WEBSITE_URL`, `PRIVACY_URL`, `TERMS_URL`: organization-approved HTTPS legal/information pages.
- Leave `TEAMS_APP_ID` empty for `teamsApp/create` to populate, or use the existing app's actual ID.

The bot/Entra app must already be created by the workshop infrastructure and configured in the host.
The lifecycle uses `botFramework/create` to register/update its channel endpoint; don't provision duplicate
bot registrations under a different identity. Re-run provisioning after changing the endpoint.
Set live Foundry/auth/reviewer environment variables on the container independently of these package variables.

## CLI workflow (PowerShell, in this directory)

Commands verified in the official ATK CLI reference and current toolkit templates. They are not tenant-tested
in this repository's offline workshop validation. Schema/action version is v1.11; manifest schema is v1.26.
Custom-engine agent availability in Copilot remains preview/tenant-policy dependent.

```powershell
npm i -g @microsoft/m365agentstoolkit-cli
$env:ATK_CLI_SKILL='true'
atk --version
atk --help
atk auth login m365
atk provision --env dev -i false
# Container code is deployed separately from repo root using the workshop azd flow.
# Here deploy only updates the application package in Developer Portal:
atk deploy --env dev -i false
atk package --env dev -i false
atk validate --env dev -i false
atk preview --env dev --m365-host teams -i false
# Submit package for tenant admin approval (does not grant consent automatically):
atk publish --env dev -i false
```

Check `atk <command> --help` for release-specific options. `atk provision`, `deploy`, `preview`,
`package`, `validate`, and `publish` are actual CLI command names, not assumed aliases.
If stable CLI predates this schema, install the documented beta with
`npm i -g @microsoft/m365agentstoolkit-cli@beta` and check its version/help before use.
Do not run provisioning/publish in mock mode; those operations create tenant resources.

`m365agents.local.yml` shares the same registration flow but uses `--env local`.
Copy `env\.env.dev` to `env\.env.local`, set `TEAMSFX_ENV=local`, and fill its actual live-mode
bot/tunnel values. Run the Python host separately; `atk deploy --env local` only updates the app package.
The toolkit does not launch Python or provision a tunnel for this deliberately deployment-agnostic package.

## Packaging / governance

`appPackage\manifest.json` uses `copilotAgents.customEngineAgents` with a bot ID matching `bots[0].botId`,
including personal and Copilot scopes. The required icons are valid 192x192 RGBA color and transparent
32x32 white outline PNGs. The endpoint is channel-registration configuration, not a made-up manifest property.
ATK expands `${{...}}` from environment files; the unexpanded manifest is a template, not upload-ready.
Generated packages go under `appPackage\build` and are ignored by source control.
Tenant administrators review/approve in Teams admin center; Copilot availability is governed by M365 policies.
Agent 365 identity/registry setup is documented separately in `..\m365-host\README.md`.

Sources: [ATK CLI](https://learn.microsoft.com/microsoftteams/platform/toolkit/microsoft-365-agents-toolkit-cli),
[toolkit templates](https://github.com/OfficeDev/microsoft-365-agents-toolkit),
[Teams manifest v1.26 schema](https://developer.microsoft.com/en-us/json-schemas/teams/v1.26/MicrosoftTeams.schema.json).
