"""Optional Agent 365 integration seams; mock mode never acquires tokens or calls MCP."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Awaitable, Callable, Iterator

from kyc_core import telemetry
from kyc_core.config import Settings
from kyc_core.governance import AuditLog, ToolPolicy

log = logging.getLogger(__name__)
TokenProvider = Callable[[str], Awaitable[str]]
ToolRegistrar = Callable[[str], Awaitable[Any]]
MailSender = Callable[[str], Awaitable[None]]


class A365Integration:
    def __init__(self, cfg: Settings, token_provider: TokenProvider | None = None,
                 tool_registrar: ToolRegistrar | None = None,
                 mail_sender: MailSender | None = None):
        self.cfg = cfg
        self.token_provider = token_provider
        self.tool_registrar = tool_registrar
        self.mail_sender = mail_sender
        self.core = None
        if cfg.is_mock:
            log.info("MOCK: Agent 365 export, agent identity and Work IQ MCP are disabled")
        else:
            telemetry.init_telemetry("kyc-m365-host")
            try:
                from microsoft_agents_a365.observability import core
                self.core = core
            except ImportError:
                log.info("Agent 365 observability unavailable; using kyc_core.telemetry")

    @contextmanager
    def scope(self, kind: str, name: str, conversation_id: str = "") -> Iterator[Any]:
        scope = None
        if self.core:
            try:
                core = self.core
                request = core.Request(conversation_id=conversation_id)
                details = core.AgentDetails(
                    agent_id=os.getenv("A365_AGENT_ID", self.cfg.foundry_agent_name),
                    agent_name=self.cfg.foundry_agent_name,
                )
                if kind == "tool":
                    scope = core.ExecuteToolScope.start(request, core.ToolCallDetails(tool_name=name), details)
                else:
                    scope = core.InvokeAgentScope.start(request, core.InvokeAgentScopeDetails(), details)
            except Exception:
                log.warning("Agent 365 preview scope API unavailable; falling back", exc_info=True)
        # Do not catch exceptions thrown by the operation or yield a second time.
        with scope if scope is not None else telemetry.span(name, operation=kind):
            yield scope

    async def acquire_token(self, scope: str) -> str | None:
        if self.cfg.is_mock:
            log.info("MOCK: agent identity token acquisition skipped")
            return None
        if not self.token_provider:
            raise RuntimeError("Configure a tenant-approved Agent ID token_provider; no implicit user token fallback")
        token = await self.token_provider(scope)
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("Agent ID token provider returned an empty token")
        return token

    async def register_work_iq(self, scope: str) -> Any:
        if self.cfg.is_mock:
            log.info("MOCK: Work IQ MCP registration skipped")
            return None
        if not self.tool_registrar:
            raise RuntimeError("Provide a Work IQ MCP registrar for the selected Agent365 framework extension")
        token = await self.acquire_token(scope)
        return await self.tool_registrar(token)

    async def notify_pending(self, sar_id: str) -> None:
        if self.cfg.is_mock:
            log.info("MOCK: compliance notification skipped (no mail sent)")
            return
        if not self.mail_sender:
            log.info("Work IQ mail hook not configured; no notification sent")
            return
        ToolPolicy(cfg=self.cfg).check("notify_compliance")
        with self.scope("tool", "notify_compliance"):
            # Pass only an opaque reference, not customer data or SAR narrative.
            await self.mail_sender(sar_id)
            AuditLog(cfg=self.cfg).write("compliance_notified", sar_id=sar_id)

