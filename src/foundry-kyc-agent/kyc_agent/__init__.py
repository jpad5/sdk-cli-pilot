"""KYC/AML compliance agent (mock + Microsoft Foundry Agent Service)."""

from __future__ import annotations

from kyc_core.agent import KycAgent
from kyc_core.config import Settings, settings


def create_agent(cfg: Settings | None = None) -> KycAgent:
    cfg = cfg or settings()
    if cfg.is_mock:
        from .mock_agent import MockKycAgent

        return MockKycAgent(cfg)
    from .foundry_agent import FoundryKycAgent

    return FoundryKycAgent(cfg)


__all__ = ["create_agent"]
