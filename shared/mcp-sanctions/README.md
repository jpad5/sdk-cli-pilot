# Synthetic KYC sanctions MCP server

Offline workshop fixture screening, **not real compliance screening**. Uses the official Python MCP SDK (`mcp.server.fastmcp.FastMCP`), RapidFuzz and `kyc_core`. No model, credentials or network requests are required by the screening tools. Both demo modes use fictional local lists; `DEMO_MODE=live` does not turn this into a production sanctions service.

## Install and run (PowerShell, repository root)

```powershell
.\.venv\Scripts\pip install -e shared\kyc_core -e shared\mcp-sanctions
# Default: stdio (stdout is reserved for MCP protocol messages).
.\.venv\Scripts\python -m kyc_sanctions.server
# Alternative package entry point:
.\.venv\Scripts\python -m kyc_sanctions
# Streamable HTTP (not legacy SSE):
.\.venv\Scripts\python -m kyc_sanctions.server --http
# Optional alternate port:
.\.venv\Scripts\python -m kyc_sanctions.server --http --port 8766
```

HTTP binds only `127.0.0.1`, defaults to port **8765**, and serves **`/mcp`**. Stop with Ctrl+C. This is an unauthenticated local demonstration server; do not expose it directly to a network.

Configuration from `kyc_core.config.settings()`:

- `KYC_MOCK_DIR`: directory containing `customers.json` and `sanctions.csv` (default `shared\mock`).
- `KYC_DATA_DIR`: audit output directory (default `.data`); tools append `audit.jsonl`.
- `KYC_REPO_ROOT`: optional repository location override, useful when launching from another working directory.

## Public API

```text
kyc_sanctions.screening.screen(name: str, dob: str | None = None,
                              country: str | None = None) -> ScreeningResult
kyc_sanctions.screening.list_sources() -> list[str]
kyc_sanctions.customers.lookup_customer(customer_id_or_name: str) -> CustomerProfile | None
```

These three functions are also exported from `kyc_sanctions`. They read local fixture files, make no network calls and do not write audit events. `ScreeningResult.screened_at` uses the core model's current UTC timestamp. Customer lookup accepts a case-insensitive ID or full name, ignoring surrounding whitespace.

MCP server name: **`kyc-sanctions`**. Registered tools:

| Tool | Parameters | Python return / MCP JSON payload |
| --- | --- | --- |
| `screen_name` | `name`, optional `dob`, optional `country` | `dict` containing serialized `ScreeningResult` |
| `lookup_customer` | `customer_id_or_name` | `dict` containing serialized `CustomerProfile`, or `None` (empty MCP content when absent) |
| `list_sources` | none | `list[str]` of distinct, sorted source names |

Every executed tool writes an `mcp_tool_call` audit record with `tool` and an `args` summary, inside a `kyc_core.telemetry.span`. Audit failures fail closed. These synthetic argument values are recorded locally; real customer data would need a separate privacy and retention policy. Server startup initializes core telemetry without console output, preserving stdio framing. Pure helper calls are intentionally not audited. Agent-level allow-list enforcement remains the caller's responsibility.

### Matching rules

Names are casefolded, accents removed, punctuation replaced with spaces and whitespace collapsed. An exact canonical name scores **1.0**; an exact alias scores **0.95**. Otherwise the best canonical/alias `rapidfuzz.fuzz.token_sort_ratio / 100` is considered as a fuzzy match. A supplied DOB or country that differs from a nonempty list value deducts **0.1 each**. Missing list values are not treated as mismatches. Fuzzy results are included only if their final score is **at least 0.80**; exact/alias results retain their match type after penalties. Each list row contributes at most one hit, sorted by descending score. Sources are reported even when there are no hits.

The shared core considers a sanction/PEP score of **0.85 or more** a hit. A fuzzy candidate is not necessarily a sanction hit. For example, `Quillhaven Robotics` (`CUST-1005`) is a near-miss negative control, while `Zoravian Umbra Tradng` is a deliberate fuzzy positive. Country comparisons normalize strings, not country-name-to-ISO aliases: use the fixture's ISO codes. DOB strings should use `YYYY-MM-DD`.

## Register with VS Code

Create or update `.vscode/mcp.json` locally with the following example (this README does not create it):

```json
{
  "servers": {
    "kyc-sanctions": {
      "type": "stdio",
      "command": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
      "args": ["-m", "kyc_sanctions.server"],
      "env": {
        "DEMO_MODE": "mock",
        "KYC_REPO_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

Start/trust the server from the MCP configuration editor or **MCP: List Servers**, then enable its tools in agent chat. If HTTP is already running, use a server entry with `"type": "http"` and `"url": "http://127.0.0.1:8765/mcp"` instead of command/args.

Reference: [VS Code MCP configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers).

## Register with GitHub Copilot CLI

In interactive Copilot CLI, run `/mcp add`. Choose **STDIO** (or **Local**, depending on CLI version), name `kyc-sanctions`, and enter the **absolute quoted path** to this repository's `.venv\Scripts\python.exe` followed by `-m kyc_sanctions.server` as the command. Set `KYC_REPO_ROOT` to the repository's absolute path and `DEMO_MODE` to `mock` in environment variables. Enable the three tools (or `*`), then save with Ctrl+S. Absolute executable paths avoid dependence on CLI working directory or venv activation.

Alternatively, start HTTP first, then use `/mcp add` with type **HTTP** and URL `http://127.0.0.1:8765/mcp`. CLI configuration is separate from VS Code configuration. Organization MCP allow-list policy may restrict registration.

Reference: [Copilot CLI MCP servers](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers).

## Register with Microsoft Foundry

Foundry Agent Service connects to **remote MCP endpoints**, not local stdio processes. Its cloud runtime cannot reach your workstation's `127.0.0.1:8765`. For this workshop, either keep local MCP clients or have your platform administrator provide an approved HTTPS reverse proxy/host reachable by Foundry (or a private endpoint through an appropriately configured Standard agent network). This package deliberately stays loopback-only and does not provision cloud infrastructure or a tunnel.

In the Foundry agent's tools configuration, add a **custom MCP server**, use server label `kyc-sanctions` and the reachable HTTPS URL ending in `/mcp`, and select `screen_name`, `lookup_customer`, and `list_sources`. Configure endpoint authentication/connection credentials as appropriate and retain tool-call approval until the server is trusted. A proxy must forward the MCP request/response and session headers; use an approved host configuration rather than disabling transport protections. Never use production customer records with this unauthenticated synthetic demo.

Reference: [Connect Foundry agents to MCP servers](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/model-context-protocol?view=foundry-current).

## Tests

```powershell
.\.venv\Scripts\pip install -e 'shared\mcp-sanctions[test]'
.\.venv\Scripts\python -m pytest shared\mcp-sanctions\tests --basetemp=shared\mcp-sanctions\.test-data -q
```

Tests isolate `KYC_DATA_DIR` with pytest `tmp_path` under the explicitly selected project-local base directory, and restore the cached settings afterwards. The suite covers fixture validation, normalization, exact/alias/fuzzy matching, negative controls, DOB/country penalties, lookup, source discovery, audit and telemetry wrappers, and in-process `FastMCP.call_tool` execution. `.test-data` is disposable test output; pytest recreates its selected base directory on each run.
