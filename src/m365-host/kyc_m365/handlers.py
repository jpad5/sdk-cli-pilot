"""Channel-independent KYC message and human-approval handlers."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from kyc_core import governance
from kyc_core.agent import KycAgent, get_agent
from kyc_core.config import Settings
from kyc_core.models import AgentReply, SarDraft

from .a365_integration import A365Integration

log = logging.getLogger(__name__)


def summary_card(reply: AgentReply) -> dict[str, Any]:
    facts = [{"title": "Decision", "value": reply.decision.value if reply.decision else "Not assessed"}]
    if reply.risk:
        facts.append({"title": "Risk", "value": f"{reply.risk.level.value} ({reply.risk.score}/100)"})
    hits = reply.screening.hits if reply.screening else []
    facts.append({"title": "Screening hits", "value": str(len(hits))})
    if reply.sar:
        facts.append({"title": "SAR", "value": f"{reply.sar.sar_id}: {reply.sar.status}"})
    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard", "version": "1.5",
        "body": [{"type": "TextBlock", "text": "KYC / AML review", "weight": "Bolder"},
                 {"type": "FactSet", "facts": facts}],
    }
    for hit in hits:
        card["body"].append({"type": "TextBlock", "wrap": True,
                             "text": f"{hit.matched_name} — {hit.list_name} ({hit.hit_type}, {hit.score:.0%})"})
    if reply.sar and reply.sar.status == "pending_approval":
        card["body"].append({"type": "TextBlock", "wrap": True,
                             "text": "Human review required. Approval records a decision; it does not file a SAR."})
        card["actions"] = [{"type": "Action.Submit", "title": title,
                            "data": {"action": action, "sar_id": reply.sar.sar_id}}
                           for title, action in (("Approve", "approve_sar"), ("Reject", "reject_sar"))]
    return card


class KycHandler:
    def __init__(self, cfg: Settings, agent: KycAgent | None = None,
                 integration: A365Integration | None = None):
        self.cfg = cfg
        self.agent = agent
        self.integration = integration or A365Integration(cfg)
        self.lock = asyncio.Lock()

    def _path(self, conversation_id: str, tenant_id: str, sar_id: str) -> Path:
        key = hashlib.sha256(json.dumps([tenant_id, conversation_id, sar_id]).encode()).hexdigest()
        return self.cfg.data_dir / "m365-approvals" / f"{key}.json"

    def _save(self, path: Path, sar: SarDraft) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        staging = path.with_suffix(".new")
        staging.write_text(sar.model_dump_json(), encoding="utf-8")
        for attempt in range(6):
            try:
                staging.replace(path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                # Windows sync/antivirus scanners can briefly hold the destination.
                time.sleep(0.05 * (attempt + 1))

    async def handle(self, text: str, conversation_id: str, user: str,
                     value: dict[str, Any] | None = None, *, tenant_id: str = "",
                     user_id: str = "") -> AgentReply:
        if value is not None:
            if not isinstance(value, dict):
                raise ValueError("Approval payload must be an object")
            return await self._approval(value, conversation_id, tenant_id, user, user_id)
        with self.integration.scope("agent", "kyc.invoke", conversation_id):
            if self.agent is None:
                self.agent = get_agent(replace(self.cfg, sar_auto_approve=False))
            reply = await self.agent.run(text, conversation_id, user)
        if reply.sar:
            async with self.lock:
                path = self._path(conversation_id, tenant_id, reply.sar.sar_id)
                existing = SarDraft.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None
                if existing and existing.status in ("approved", "rejected"):
                    sar = existing
                else:
                    # Agent output and auto-policy cannot bypass the channel's human gate.
                    sar = governance.require_approval(reply.sar.model_copy(update={"approved_by": None}),
                        cfg=replace(self.cfg, sar_auto_approve=False))
                    self._save(path, sar)
            reply = reply.model_copy(update={"sar": sar})
            if sar.status == "pending_approval":
                try:
                    await self.integration.notify_pending(sar.sar_id)
                except Exception:
                    log.warning("Compliance notification failed; SAR remains pending for review")
                    governance.AuditLog(cfg=self.cfg).write("compliance_notification_failed", sar_id=sar.sar_id)
        return reply

    async def _approval(self, value: dict[str, Any], conversation_id: str, tenant_id: str,
                        user: str, user_id: str) -> AgentReply:
        action, sar_id = value.get("action"), value.get("sar_id")
        if action not in ("approve_sar", "reject_sar") or not isinstance(sar_id, str):
            raise ValueError("Unknown approval action")
        if not user.strip():
            raise PermissionError("A named reviewer is required")
        if not self.cfg.is_mock:
            reviewers = {v.strip() for v in os.getenv("KYC_REVIEWER_IDS", "").split(",") if v.strip()}
            if not tenant_id or tenant_id != os.getenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID") or user_id not in reviewers:
                governance.AuditLog(cfg=self.cfg).write("sar_approval_denied", sar_id=sar_id)
                raise PermissionError("Reviewer is not authorized in this tenant")
        path = self._path(conversation_id, tenant_id, sar_id)
        async with self.lock:
            if not path.exists():
                raise ValueError("No pending SAR in this conversation")
            sar = SarDraft.model_validate_json(path.read_text(encoding="utf-8"))
            if sar.status != "pending_approval":
                raise ValueError("This SAR was already reviewed")
            with self.integration.scope("tool", "sar.review", conversation_id):
                if action == "approve_sar":
                    sar = governance.require_approval(sar, approver=user, cfg=self.cfg)
                else:
                    sar = sar.model_copy(update={"status": "rejected", "approved_by": None})
                    governance.AuditLog(cfg=self.cfg).write("sar_rejected", sar_id=sar_id,
                        customer_id=sar.customer_id, reviewer=user)
                self._save(path, sar)
        return AgentReply(text=f"SAR {sar.sar_id} {sar.status} by {user}. No regulatory filing was submitted.", sar=sar)




