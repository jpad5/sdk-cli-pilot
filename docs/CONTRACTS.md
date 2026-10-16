# Component contracts

Every component builds against these contracts so that each one can be developed and tested on its own.

## Mode switch
- `DEMO_MODE=mock` (default) or `DEMO_MODE=live`. Read it via `kyc_core.config.settings()`.
- In mock mode, no network calls are made: no Azure, no Graph, no GitHub API.

## Shared Python package: `shared/kyc_core`
Installable with `pip install -e shared/kyc_core`. Import name: `kyc_core`.

| Module | Provides |
|--------|----------|
| `kyc_core.config` | `settings()` returns a `Settings` dataclass, loaded from env / `.env` |
| `kyc_core.models` | Pydantic models: `CustomerProfile`, `ScreeningHit`, `ScreeningResult`, `RiskAssessment`, `KycDecision`, `SarDraft`, `AgentReply` |
| `kyc_core.agent` | `KycAgent` protocol: `async def run(message: str, conversation_id: str, user: str) -> AgentReply` and `get_agent(settings) -> KycAgent` (mock or Foundry; the Foundry implementation is in `src/foundry-kyc-agent`) |
| `kyc_core.governance` | `ToolPolicy` (allow-list), `AuditLog` (JSONL append, `.data/audit.jsonl`), `require_approval(sar: SarDraft)` (human-in-the-loop) |
| `kyc_core.telemetry` | `init_telemetry(service_name)`, `span(name, **attrs)`. Uses the Agent 365 observability SDK when available, otherwise OpenTelemetry to the console / OTLP |

## Mock data: `shared/mock`
- `customers.json`: synthetic customer profiles (clean, PEP, sanctioned, high-risk jurisdiction)
- `sanctions.csv`: synthetic sanctions/PEP list (`name,aliases,list,country,dob,type`)
- `llm_responses.json`: canned replies keyed by intent

## Sanctions MCP server: `shared/mcp-sanctions`
- FastMCP server `kyc-sanctions`. Transports: stdio (default) and streamable HTTP on `:8765/mcp`
- Tools: `screen_name(name: str, dob?: str, country?: str) -> ScreeningResult`, `list_sources() -> list[str]`

- Python package `kyc_sanctions` (`pip install -e shared/mcp-sanctions`):
  - `kyc_sanctions.screening.screen(name: str, dob: str | None = None, country: str | None = None) -> kyc_core.ScreeningResult`: a pure function with no network access, which reads `settings().mock_dir / "sanctions.csv"`
  - `kyc_sanctions.customers.lookup_customer(customer_id_or_name: str) -> kyc_core.CustomerProfile | None`
  - `python -m kyc_sanctions.server [--http]` starts the MCP server

## KYC agent package: `src/foundry-kyc-agent` (import `kyc_agent`)
- `kyc_agent.create_agent(cfg: Settings) -> KycAgent` returns a `MockKycAgent` (deterministic, local tools) or a `FoundryKycAgent` (azure-ai-projects)
- `kyc_agent.tools`: `risk_score(profile, screening) -> RiskAssessment`, `draft_sar(...) -> SarDraft`. Every tool call goes through `ToolPolicy.check` and the `AuditLog`, and uses `require_approval` for SARs.
- CLI: `python -m kyc_agent chat "<message>"`
- Evals: `python -m kyc_agent.evals [--mode mock|live] [--threshold 0.8]` writes `.data/eval-results.json` and exits non-zero below the threshold

## Ports
- M365 host: `3978` (`/api/messages`)
- MCP sanctions HTTP: `8765`
- OTLP collector (optional): `4317`
