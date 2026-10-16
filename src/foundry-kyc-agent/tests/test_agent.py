from __future__ import annotations

from dataclasses import replace

import pytest

from kyc_agent import create_agent, tools
from kyc_agent.evals import run_evals
from kyc_agent.mock_agent import MockKycAgent
from kyc_core.governance import AuditLog
from kyc_core.governance import ToolNotAllowedError
from kyc_core.models import KycDecision, RiskLevel

EXPECTED = {
    "CUST-1001": (KycDecision.APPROVE, False),
    "CUST-1002": (KycDecision.ENHANCED_DUE_DILIGENCE, False),
    "CUST-1003": (KycDecision.REJECT, True),
    "CUST-1004": (KycDecision.REJECT, True),
    "CUST-1005": (KycDecision.APPROVE, False),
    "CUST-1006": (KycDecision.ESCALATE_SAR, True),
    "CUST-1007": (KycDecision.ESCALATE_SAR, True),
    "CUST-1008": (KycDecision.ENHANCED_DUE_DILIGENCE, False),
}


def test_factory_returns_mock(cfg):
    assert isinstance(create_agent(cfg), MockKycAgent)


@pytest.mark.parametrize("customer_id", EXPECTED)
async def test_decision_per_customer(cfg, customer_id):
    reply = await MockKycAgent(cfg).run(f"onboard {customer_id}", "c1", "tester")
    decision, has_sar = EXPECTED[customer_id]
    assert reply.decision == decision
    assert (reply.sar is not None) == has_sar
    assert "Sources checked" in reply.text


def test_risk_score_is_explainable(cfg):
    profile = tools.lookup_customer("CUST-1007", cfg=cfg)
    screening = tools.screen_name(profile.full_name, country=profile.country, cfg=cfg)
    risk = tools.risk_score(profile, screening, cfg=cfg)
    assert risk.level == RiskLevel.HIGH
    assert sum(int(f.rsplit("+", 1)[1].rstrip(")")) for f in risk.factors) == risk.score


def test_sanction_is_prohibited(cfg):
    profile = tools.lookup_customer("CUST-1003", cfg=cfg)
    risk = tools.risk_score(profile, tools.screen_name(profile.full_name, cfg=cfg), cfg=cfg)
    assert risk.level == RiskLevel.PROHIBITED and risk.score == 100


def test_blocked_tool_is_denied_and_audited(cfg):
    restricted = replace(cfg, allowed_tools=("lookup_customer",))
    with pytest.raises(ToolNotAllowedError):
        tools.screen_name("anyone", cfg=restricted)
    last = AuditLog(cfg=cfg).read()[-1]
    assert last["event"] == "tool_blocked" and last["tool"] == "screen_name"


async def test_sar_requires_named_approver(cfg):
    agent = MockKycAgent(cfg)
    reply = await agent.run("onboard CUST-1003", "c1", "analyst")
    assert reply.sar.status == "pending_approval" and reply.sar.approved_by is None
    approved = await agent.run(f"approve {reply.sar.sar_id} as Jane Compliance", "c1", "analyst")
    assert approved.sar.status == "approved" and approved.sar.approved_by == "Jane Compliance"
    events = [e["event"] for e in AuditLog(cfg=cfg).read()]
    assert "sar_pending_approval" in events and "sar_approved" in events


async def test_auto_approve_policy(cfg):
    reply = await MockKycAgent(replace(cfg, sar_auto_approve=True)).run("onboard CUST-1006", "c", "u")
    assert reply.sar.approved_by == "auto-policy"


async def test_unknown_customer(cfg):
    reply = await MockKycAgent(cfg).run("onboard Nobody At All", "c", "u")
    assert reply.decision is None and "CUST-1001" in reply.text


async def test_approve_missing_sar(cfg):
    reply = await MockKycAgent(cfg).run("approve SAR-DEADBEEF as Bob", "c", "u")
    assert "not found" in reply.text


async def test_evals_pass_in_mock_mode(cfg):
    out = await run_evals("mock", cfg=cfg)
    assert out["summary"]["pass_rate"] == 1.0, out["summary"]["cases"]


def test_live_requires_endpoint(cfg):
    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        create_agent(replace(cfg, demo_mode="live", foundry_project_endpoint=""))
