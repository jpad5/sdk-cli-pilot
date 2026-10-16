"""Shared KYC workflow used by the mock agent and as local tool execution for the Foundry agent."""

from __future__ import annotations

import json
import re

from kyc_core.config import Settings
from kyc_core.models import AgentReply, KycDecision
from kyc_core.telemetry import current_trace_id, span

from . import tools

CUSTOMER_ID = re.compile(r"\bCUST-\d+\b", re.I)
SUBJECT = re.compile(r"\b(?:onboard|screen|check|assess|review)\s+(?:customer\s+)?(.+)", re.I)
APPROVE = re.compile(r"\bapprove\s+(SAR-[0-9A-F]+)\s+as\s+(.+)", re.I)


def parse_subject(message: str) -> str | None:
    if m := CUSTOMER_ID.search(message):
        return m.group(0).upper()
    if m := SUBJECT.search(message):
        return m.group(1).strip().strip(".?!\"'")
    return None


def templates(cfg: Settings) -> dict[str, str]:
    return json.loads((cfg.mock_dir / "llm_responses.json").read_text(encoding="utf-8-sig"))


def assess(subject: str, cfg: Settings) -> AgentReply:
    calls: list[str] = []
    with span("kyc.assess", **{"kyc.subject": subject}):
        profile = tools.lookup_customer(subject, cfg=cfg)
        calls.append("lookup_customer")
        if profile is None:
            return AgentReply(text=templates(cfg)["unknown"], tool_calls=calls, trace_id=current_trace_id())
        screening = tools.screen_name(profile.full_name, dob=profile.dob, country=profile.country, cfg=cfg)
        risk = tools.risk_score(profile, screening, cfg=cfg)
        calls += ["screen_name", "risk_score"]
        decision = tools.decide(profile, screening, risk)
        sar = None
        if decision in (KycDecision.REJECT, KycDecision.ESCALATE_SAR):
            sar = tools.submit_sar(tools.draft_sar(profile, screening, risk, cfg=cfg), cfg=cfg)
            calls.append("draft_sar")
        text = templates(cfg)[decision.value].format(customer_name=profile.full_name)
        text += f"\nRisk: {risk.score}/100 ({risk.level.value})"
        if risk.factors:
            text += " - " + "; ".join(risk.factors)
        text += f"\nSources checked: {', '.join(screening.sources_checked)}"
        if sar:
            text += f"\nSAR {sar.sar_id} is {sar.status.replace('_', ' ')}."
        return AgentReply(
            text=text, decision=decision, risk=risk, screening=screening, sar=sar,
            tool_calls=calls, trace_id=current_trace_id(),
        )


def approve(sar_id: str, approver: str, cfg: Settings) -> AgentReply:
    with span("kyc.approve_sar", **{"kyc.sar_id": sar_id}):
        sar = tools.approve_sar(sar_id, approver.strip(), cfg=cfg)
    if sar is None:
        return AgentReply(text=f"SAR {sar_id.upper()} was not found.", trace_id=current_trace_id())
    return AgentReply(text=f"SAR {sar.sar_id} approved by {sar.approved_by}.", sar=sar, trace_id=current_trace_id())
