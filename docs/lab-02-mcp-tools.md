# Lab 2 - Add tools via MCP (sanctions screening)

**Pillar:** Build · **Featured:** MCP Python SDK (`FastMCP`), Foundry `MCPTool`, VS Code MCP

## 1. Run the MCP server

```powershell
.\.venv\Scripts\python -m kyc_sanctions.server --http      # http://127.0.0.1:8765/mcp
```

The server exposes three tools: `screen_name`, `lookup_customer` and `list_sources`. Matching uses normalization, alias handling and RapidFuzz (see [README](../shared/mcp-sanctions/README.md)).

## 2. Use it from GitHub Copilot in VS Code

Add the following to `.vscode/mcp.json`:

```json
{ "servers": { "kyc-sanctions": { "type": "http", "url": "http://127.0.0.1:8765/mcp" } } }
```

Then ask Copilot Chat in agent mode: *"Screen 'Zoravian Umbra Tradng' against the sanctions list."* The fuzzy match catches the misspelling.

Try the near miss next: *"Screen 'Quillhaven Robotics'."* It should come back as not a hit.

## 3. Use it from the Foundry agent (live)

Foundry calls MCP servers from the cloud, so the server must be publicly reachable. One option is to expose it through a dev tunnel:

```powershell
devtunnel host -p 8765 --allow-anonymous
$env:MCP_SANCTIONS_URL = 'https://<tunnel>/mcp'
.\.venv\Scripts\python -m kyc_agent deploy     # adds MCPTool(server_label="kyc_sanctions", ...)
```

Leaving the tunnel anonymous is fine for the workshop's synthetic data only. Never expose a real screening service this way.

## 4. Tests

```powershell
.\.venv\Scripts\python -m pytest shared\mcp-sanctions\tests -q -p no:cacheprovider
```
