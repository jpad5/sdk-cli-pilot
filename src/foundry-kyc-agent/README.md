# Foundry KYC/AML agent (`kyc_agent`)

The core reasoning agent for the workshop. It is built with the **Microsoft Foundry SDK** (`azure-ai-projects` 2.x) and uses **synthetic data only**.

| Mode | What runs |
| --- | --- |
| `DEMO_MODE=mock` (default) | `MockKycAgent`: deterministic rule engine plus canned narrative text. No cloud or credentials. |
| `DEMO_MODE=live` | `FoundryKycAgent`: a prompt agent version in a Foundry project, using the Responses API with a local function-tool loop. |

In both modes the same **governed tools** run locally (`kyc_agent/tools.py`):

- `lookup_customer`
- `screen_name`
- `risk_score`
- `draft_sar`

Every call passes the `kyc_core` tool allow-list, is wrapped in an OpenTelemetry span, and writes an audit record. As a result, the governance controls in Lab 9 behave the same whether or not a model is involved.

## Install and run (PowerShell, from the repository root)

```powershell
.\.venv\Scripts\python -m pip install -e shared\kyc_core -e shared\mcp-sanctions -e src\foundry-kyc-agent
$env:DEMO_MODE = 'mock'
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1003"            # REJECT, exact sanctions hit
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1007"            # ESCALATE_SAR, pending human approval
.\.venv\Scripts\python -m kyc_agent chat "approve SAR-XXXXXXXX as alice"  # HITL approval
.\.venv\Scripts\python -m pytest src\foundry-kyc-agent\tests -q -p no:cacheprovider
```

## Evaluations (Lab 6)

```powershell
.\.venv\Scripts\python -m kyc_agent.evals --mode mock --threshold 0.8
```

The evals run `evals/dataset.jsonl` (10 labelled cases) through the agent. A custom AML grader (`kyc_agent/evals/grader.py`) scores each case on two things:

- **Decision accuracy**
- **Safety:** the agent must never approve a sanctioned party, and every SAR must stay `pending_approval`.

The CLI writes `.data/eval-results.json` and an `eval_gate` audit record, and exits 1 if the score falls below the threshold. The GitHub Actions eval gate uses that exit code. In live mode, you can also upload the same dataset to Foundry evaluations to see the results in the portal.

## Live mode (Lab 1)

1. Provision with `azd up` from the repository root, which deploys `infra/` (Foundry account and project, model deployment, App Insights).
2. Copy `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT` from `.env.azd` into `.env`.
3. Sign in with `az login`, then:

```powershell
$env:DEMO_MODE = 'live'
.\.venv\Scripts\python -m kyc_agent deploy            # project.agents.create_version(...)
.\.venv\Scripts\python -m kyc_agent chat "Assess CUST-1006"
```

`deploy` creates or updates a versioned `PromptAgentDefinition` named `$FOUNDRY_AGENT_NAME` (default `kyc-aml-agent`). It declares the governed function tools and, if `MCP_SANCTIONS_URL` is a publicly reachable URL, also adds a Foundry `MCPTool` for the sanctions server. Chat uses `openai.conversations.create()` and `openai.responses.create(..., extra_body={"agent_reference": ...})`. Function calls are executed locally and returned as `function_call_output` items.

### Alternative: `azd ai agent`

The Azure Developer CLI AI agent extension can scaffold and deploy hosted agents from the CLI:

```powershell
azd extension install azure.ai.agents
azd ai agent init      # pick a template or point at an agent definition
azd up                 # provision the Foundry project and deploy
```

The workshop uses the SDK path so attendees can see each API call. Use `azd ai agent` to show the CLI-first equivalent.

## Layout

```text
kyc_agent/
  tools.py          governed tools, risk rules, SAR store, approval
  workflow.py       assess()/approve() shared by mock and live agents
  mock_agent.py     deterministic agent (no cloud)
  foundry_agent.py  Foundry SDK agent (deploy + Responses tool loop)
  evals/            AML grader + eval gate CLI
evals/dataset.jsonl
tests/
```
