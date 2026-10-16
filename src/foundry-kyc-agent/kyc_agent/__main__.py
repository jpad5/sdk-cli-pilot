from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from kyc_core.config import settings
from kyc_core.governance import ToolNotAllowedError
from kyc_core.telemetry import init_telemetry

from . import create_agent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kyc_agent")
    sub = parser.add_subparsers(dest="command", required=True)
    chat = sub.add_parser("chat", help="Send one message to the KYC agent")
    chat.add_argument("message", nargs="+")
    chat.add_argument("--user", default="workshop-analyst")
    sub.add_parser("deploy", help="Create/update the agent version in Microsoft Foundry (live mode)")
    args = parser.parse_args(argv)

    init_telemetry("kyc-agent")
    cfg = settings()
    if args.command == "deploy":
        if cfg.is_mock:
            print("DEMO_MODE=mock: nothing to deploy. Set DEMO_MODE=live and FOUNDRY_PROJECT_ENDPOINT.")
            return 0
        from .foundry_agent import FoundryKycAgent

        agent = FoundryKycAgent(cfg).deploy()
        print(f"Deployed agent {agent.name} version {agent.version} (id {agent.id})")
        return 0

    try:
        reply = asyncio.run(create_agent(cfg).run(" ".join(args.message), f"cli-{uuid.uuid4().hex[:8]}", args.user))
    except ToolNotAllowedError as exc:
        print(f"BLOCKED by governance policy: {exc}. The attempt was written to the audit log.")
        return 2
    print(reply.text)
    if reply.decision:
        print(f"[decision={reply.decision.value} tools={','.join(reply.tool_calls)} mode={cfg.demo_mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
