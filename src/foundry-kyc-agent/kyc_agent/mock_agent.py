from __future__ import annotations

from kyc_core.config import Settings, settings
from kyc_core.models import AgentReply
from kyc_core.telemetry import span

from . import workflow


class MockKycAgent:
    """Deterministic agent: same tools and governance as live, no model call."""

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or settings()

    async def run(self, message: str, conversation_id: str, user: str) -> AgentReply:
        with span("agent.invoke", **{"gen_ai.agent.name": self.cfg.foundry_agent_name, "kyc.mode": "mock",
                                      "kyc.conversation_id": conversation_id}):
            if m := workflow.APPROVE.search(message):
                return workflow.approve(m.group(1), m.group(2), self.cfg)
            subject = workflow.parse_subject(message)
            if not subject:
                return AgentReply(text=workflow.templates(self.cfg)["unknown"])
            return workflow.assess(subject, self.cfg)
