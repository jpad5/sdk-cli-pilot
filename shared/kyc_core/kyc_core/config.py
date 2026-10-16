from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _find_repo_root() -> Path:
    env_root = os.environ.get("KYC_REPO_ROOT")
    if env_root:
        return Path(env_root)
    for parent in Path(__file__).resolve().parents:
        if (parent / "docs" / "CONTRACTS.md").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _find_repo_root()


@dataclass(frozen=True)
class Settings:
    demo_mode: str = "mock"
    foundry_project_endpoint: str = ""
    foundry_model_deployment: str = "gpt-4.1-mini"
    foundry_agent_name: str = "kyc-aml-agent"
    mcp_sanctions_url: str = "http://localhost:8765/mcp"
    appinsights_connection_string: str = ""
    otlp_endpoint: str = ""
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / ".data")
    mock_dir: Path = field(default_factory=lambda: REPO_ROOT / "shared" / "mock")
    allowed_tools: tuple[str, ...] = ("screen_name", "risk_score", "draft_sar", "lookup_customer")
    sar_auto_approve: bool = False

    @property
    def is_mock(self) -> bool:
        return self.demo_mode != "live"


@lru_cache(maxsize=1)
def settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env", override=False)
    env = os.environ
    allowed = env.get("KYC_ALLOWED_TOOLS")
    return Settings(
        demo_mode=env.get("DEMO_MODE", "mock").lower(),
        foundry_project_endpoint=env.get("FOUNDRY_PROJECT_ENDPOINT", ""),
        foundry_model_deployment=env.get("FOUNDRY_MODEL_DEPLOYMENT", "gpt-4.1-mini"),
        foundry_agent_name=env.get("FOUNDRY_AGENT_NAME", "kyc-aml-agent"),
        mcp_sanctions_url=env.get("MCP_SANCTIONS_URL", "http://localhost:8765/mcp"),
        appinsights_connection_string=env.get("APPLICATIONINSIGHTS_CONNECTION_STRING", ""),
        otlp_endpoint=env.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        data_dir=Path(env.get("KYC_DATA_DIR", str(REPO_ROOT / ".data"))),
        mock_dir=Path(env.get("KYC_MOCK_DIR", str(REPO_ROOT / "shared" / "mock"))),
        allowed_tools=tuple(t.strip() for t in allowed.split(",") if t.strip()) if allowed else Settings.allowed_tools,
        sar_auto_approve=env.get("SAR_AUTO_APPROVE", "false").lower() == "true",
    )
