# Lab 3 - Host in Microsoft 365 / Teams

**Pillar:** Build · **Featured:** M365 Agents SDK (Python), M365 Agents Toolkit CLI (`atk`), Agents Playground

## 1. Run the host locally (mock)

```powershell
$env:DEMO_MODE = 'mock'
.\.venv\Scripts\python -m kyc_m365.app            # http://127.0.0.1:3978/api/messages
curl.exe http://127.0.0.1:3978/healthz
```

Connect the **Microsoft 365 Agents Playground** (`agentsplayground`) to `/api/messages`, then send:

- `Assess CUST-1007` returns an Adaptive Card with **Approve / Reject** buttons for the SAR. This is the human-in-the-loop step.
- `Assess CUST-1003` returns a REJECT with the sanctions evidence.

Code: [app.py](../src/m365-host/kyc_m365/app.py), [handlers.py](../src/m365-host/kyc_m365/handlers.py).

## 2. Package and deploy with ATK (live)

```powershell
npm i -g @microsoft/m365agentstoolkit-cli
cd src\atk-app
atk auth login m365
atk provision --env dev -i false     # Entra app + Azure Bot registration
atk deploy    --env dev -i false
atk validate  --env dev -i false     # manifest validation
atk preview   --env dev --m365-host teams -i false
```

Point the bot messaging endpoint at the Container App from `azd deploy`, which is the `BOT_MESSAGES_ENDPOINT` output. Alternatively, use a dev tunnel to port 3978.

## 3. Container

```powershell
docker build -f src\m365-host\Dockerfile -t fsi-kyc-m365 .
docker run --rm -p 127.0.0.1:3978:3978 -e DEMO_MODE=mock fsi-kyc-m365
azd deploy m365-host       # live: pushes to ACR and updates the Container App
```
