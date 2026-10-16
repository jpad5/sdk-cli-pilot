from __future__ import annotations

from typing import Protocol, runtime_checkable

from .config import Settings, settings
from .models import AgentReply


@runtime_checkable
class KycAgent(Protocol):
    async def run(self, message: str, conversation_id: str, user: str) -> AgentReply: ...


def get_agent(cfg: Settings | None = None) -> KycAgent:
    """Return the mock or Foundry-backed KYC agent depending on DEMO_MODE.

    Concrete implementations live in `src/foundry-kyc-agent` (package `kyc_agent`).
    """
    cfg = cfg or settings()
    from kyc_agent import create_agent  # type: ignore

    return create_agent(cfg)
