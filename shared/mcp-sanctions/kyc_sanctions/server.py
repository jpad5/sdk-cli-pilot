from __future__ import annotations

import argparse

from kyc_core.governance import AuditLog
from kyc_core.telemetry import init_telemetry, span
from mcp.server.fastmcp import FastMCP

from .customers import lookup_customer as _lookup_customer
from .screening import list_sources as _list_sources, screen

mcp = FastMCP("kyc-sanctions", host="127.0.0.1", port=8765, streamable_http_path="/mcp")


@mcp.tool()
def screen_name(name: str, dob: str | None = None, country: str | None = None) -> dict:
    """Screen a name against fictional local sanctions, PEP and adverse-media lists."""
    with span("mcp.screen_name", tool="screen_name"):
        AuditLog().write("mcp_tool_call", tool="screen_name", args={"name": name, "dob": dob, "country": country})
        return screen(name, dob, country).model_dump(mode="json")


@mcp.tool()
def lookup_customer(customer_id_or_name: str) -> dict | None:
    """Look up a synthetic customer by case-insensitive ID or full name."""
    with span("mcp.lookup_customer", tool="lookup_customer"):
        AuditLog().write("mcp_tool_call", tool="lookup_customer", args={"customer_id_or_name": customer_id_or_name})
        profile = _lookup_customer(customer_id_or_name)
        return profile.model_dump(mode="json") if profile is not None else None


@mcp.tool()
def list_sources() -> list[str]:
    """List the distinct fictional screening sources available locally."""
    with span("mcp.list_sources", tool="list_sources"):
        AuditLog().write("mcp_tool_call", tool="list_sources", args={})
        return _list_sources()


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic KYC sanctions MCP server")
    parser.add_argument("--http", action="store_true", help="Use loopback streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default: 8765)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    mcp.settings.port = args.port
    init_telemetry("kyc-sanctions")
    mcp.run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
