"""Pro-code client for the low-code Copilot Studio "Customer Intake" agent.

Shows the M365 Agents SDK CopilotStudioClient: a pro-code app (or another agent)
talks directly to a Copilot Studio agent, collects intake details, then hands the
case to the pro-code KYC agent (Foundry). In mock mode the Copilot Studio side is simulated.

Usage:
    python src/copilot-studio-intake/intake_client.py "I want to open a business account for Northwind Trading"
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid

from kyc_core import settings
from kyc_core.governance import AuditLog
from kyc_core.telemetry import init_telemetry, span

MOCK_INTAKE_SCRIPT = [
    "Hi! I'm the Contoso Bank intake assistant (Copilot Studio).",
    "I've captured your request and collected the basic onboarding details.",
]


def _acquire_token(app_client_id: str, tenant_id: str) -> str:
    from msal import PublicClientApplication  # type: ignore

    pca = PublicClientApplication(client_id=app_client_id, authority=f"https://login.microsoftonline.com/{tenant_id}")
    scopes = ["https://api.powerplatform.com/.default"]
    accounts = pca.get_accounts()
    result = pca.acquire_token_silent(scopes, account=accounts[0]) if accounts else None
    if not result:
        result = pca.acquire_token_interactive(scopes=scopes)
    if "access_token" not in result:
        raise RuntimeError(f"Token acquisition failed: {result.get('error_description')}")
    return result["access_token"]


async def ask_copilot_studio(message: str) -> list[str]:
    """Send one message to the Copilot Studio agent and return its text replies."""
    if settings().is_mock:
        return [*MOCK_INTAKE_SCRIPT, f"Handing off to the KYC compliance agent: \"{message}\""]

    from microsoft_agents.activity import ActivityTypes  # type: ignore
    from microsoft_agents.copilotstudio.client import ConnectionSettings, CopilotClient  # type: ignore

    env = os.environ
    conn = ConnectionSettings(
        environment_id=env["COPILOTSTUDIOAGENT__ENVIRONMENTID"],
        agent_identifier=env["COPILOTSTUDIOAGENT__SCHEMANAME"],
        cloud=None,
        copilot_agent_type=None,
        custom_power_platform_cloud=None,
    )
    token = _acquire_token(env["COPILOTSTUDIOAGENT__AGENTAPPID"], env["COPILOTSTUDIOAGENT__TENANTID"])
    client = CopilotClient(conn, token)

    replies: list[str] = []
    conversation_id = None
    async for activity in client.start_conversation(True):
        conversation_id = activity.conversation.id if activity.conversation else conversation_id
        if activity.text:
            replies.append(activity.text)
    async for reply in client.ask_question(message, conversation_id):
        if reply.type == ActivityTypes.message and reply.text:
            replies.append(reply.text)
    return replies


def extract_subject(message: str) -> str:
    """Best-effort extraction of the customer name/id the intake is about."""
    if m := re.search(r"CUST-\d+", message, re.I):
        return m.group(0).upper()
    if m := re.search(r"(?:for|onboard|screen)\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*)", message):
        return m.group(1)
    return message


async def main(message: str) -> int:
    init_telemetry("copilot-studio-intake")
    audit = AuditLog()
    conversation_id = f"intake-{uuid.uuid4().hex[:8]}"
    with span("intake.copilot_studio", mode=settings().demo_mode):
        for text in await ask_copilot_studio(message):
            print(f"[Copilot Studio] {text}")
    audit.write("intake_handoff", conversation_id=conversation_id, source="copilot-studio")

    try:
        from kyc_core.agent import get_agent

        agent = get_agent()
    except ImportError:
        print("[handoff] kyc_agent not installed - run scripts/setup.ps1 first.")
        return 1
    with span("intake.handoff_to_kyc", conversation_id=conversation_id):
        reply = await agent.run(f"onboard {extract_subject(message)}", conversation_id, user="intake-agent")
    print(f"[KYC agent] {reply.text}")
    return 0


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "I want to open an account for CUST-1001"
    sys.exit(asyncio.run(main(msg)))
