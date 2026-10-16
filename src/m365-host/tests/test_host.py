from dataclasses import replace
from pathlib import Path
import importlib.util

import pytest
from aiohttp.test_utils import TestClient, TestServer

from kyc_core.config import Settings
from kyc_core.governance import AuditLog
from kyc_core.models import AgentReply, KycDecision, RiskAssessment, SarDraft, ScreeningResult
from kyc_m365.app import create_app
from kyc_m365.handlers import KycHandler, summary_card
from kyc_m365.a365_integration import A365Integration


class StubAgent:
    def __init__(self):
        self.calls = []

    async def run(self, message, conversation_id, user):
        self.calls.append((message, conversation_id, user))
        return AgentReply(text="Escalate for human review", decision=KycDecision.ESCALATE_SAR,
            risk=RiskAssessment(customer_id="C1", score=95, level="high"),
            screening=ScreeningResult(query_name="Synthetic Customer"),
            sar=SarDraft(sar_id="SAR1", customer_id="C1", summary="Synthetic", indicators=["test"]))


@pytest.fixture
def cfg():
    # Keep all test artifacts inside this project, never OS temporary directories.
    from uuid import uuid4
    import shutil
    path = Path(__file__).parent / ".runs" / str(uuid4())
    yield Settings(data_dir=path)
    shutil.rmtree(path, ignore_errors=True)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


@pytest.mark.asyncio
async def test_handler_returns_text_card_and_stores_pending(cfg):
    stub = StubAgent()
    handler = KycHandler(cfg, stub)
    reply = await handler.handle("screen C1", "conversation", "Analyst")
    card = summary_card(reply)
    assert reply.text and reply.sar.status == "pending_approval"
    assert len(card["actions"]) == 2
    assert stub.calls == [("screen C1", "conversation", "Analyst")]
    assert AuditLog(cfg=cfg).read()[-1]["event"] == "sar_pending_approval"


@pytest.mark.asyncio
async def test_approval_calls_governance_and_audits(cfg, monkeypatch):
    from kyc_core import governance
    handler = KycHandler(cfg, StubAgent())
    await handler.handle("screen", "conversation", "Analyst")
    real = governance.require_approval
    seen = []
    def spy(sar, approver=None, cfg=None):
        seen.append(approver)
        return real(sar, approver=approver, cfg=cfg)
    monkeypatch.setattr(governance, "require_approval", spy)
    # A new handler proves the pending draft survives process/handler recreation.
    reply = await KycHandler(cfg, StubAgent()).handle("", "conversation", "Teams Reviewer",
        {"action": "approve_sar", "sar_id": "SAR1"})
    assert seen == ["Teams Reviewer"]
    assert reply.sar.status == "approved" and reply.sar.approved_by == "Teams Reviewer"
    assert AuditLog(cfg=cfg).read()[-1]["event"] == "sar_approved"
    with pytest.raises(ValueError, match="already reviewed"):
        await handler.handle("", "conversation", "Reviewer", {"action": "reject_sar", "sar_id": "SAR1"})


@pytest.mark.asyncio
async def test_reject_and_conversation_binding(cfg):
    handler = KycHandler(cfg, StubAgent())
    await handler.handle("screen", "conversation", "Analyst")
    with pytest.raises(ValueError, match="No pending SAR"):
        await handler.handle("", "other-conversation", "Reviewer", {"action": "approve_sar", "sar_id": "SAR1"})
    reply = await handler.handle("", "conversation", "Reviewer", {"action": "reject_sar", "sar_id": "SAR1"})
    assert reply.sar.status == "rejected"
    assert AuditLog(cfg=cfg).read()[-1]["event"] == "sar_rejected"


@pytest.mark.asyncio
async def test_auto_approve_cannot_bypass_teams_hitl(cfg):
    handler = KycHandler(replace(cfg, sar_auto_approve=True), StubAgent())
    assert (await handler.handle("screen", "c", "a")).sar.status == "pending_approval"


@pytest.mark.asyncio
async def test_unauthorized_live_reviewer(cfg):
    mock = KycHandler(cfg, StubAgent())
    await mock.handle("screen", "c", "a")
    live = KycHandler(replace(cfg, demo_mode="live"), StubAgent())
    with pytest.raises(PermissionError):
        await live.handle("", "c", "Reviewer", {"action": "approve_sar", "sar_id": "SAR1"})


def activity(**updates):
    data = {"type": "message", "id": "msg1", "channelId": "emulator",
            "serviceUrl": "http://127.0.0.1:1", "from": {"id": "u1", "name": "Teams Analyst"},
            "recipient": {"id": "bot"}, "conversation": {"id": "conversation"},
            "text": "screen C1", "deliveryMode": "expectReplies"}
    data.update(updates)
    return data


@pytest.mark.asyncio
async def test_sdk_http_message_card_approval_and_health(cfg):
    stub = StubAgent()
    async with TestClient(TestServer(create_app(cfg, KycHandler(cfg, stub)))) as client:
        response = await client.get("/healthz")
        assert response.status == 200 and (await response.json())["mode"] == "mock"
        response = await client.post("/api/messages", json=activity())
        body = await response.json()
        assert response.status == 200, body
        assert len(body["activities"]) == 2
        assert body["activities"][0]["text"] == "Escalate for human review"
        assert body["activities"][1]["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
        response = await client.post("/api/messages", json=activity(text="", value={"action": "approve_sar", "sar_id": "SAR1"}))
        assert response.status == 200
        assert "approved by Teams Analyst" in (await response.json())["activities"][0]["text"]


@pytest.mark.asyncio
async def test_welcome(cfg):
    async with TestClient(TestServer(create_app(cfg, KycHandler(cfg, StubAgent())))) as client:
        response = await client.post("/api/messages", json=activity(type="conversationUpdate", membersAdded=[{"id": "u1"}]))
        assert response.status == 200
        assert "Welcome" in (await response.json())["activities"][0]["text"]


@pytest.mark.asyncio
async def test_mock_hooks_never_call_live_providers(cfg):
    async def forbidden(*args):
        pytest.fail("Mock mode called a live provider")
    hooks = A365Integration(cfg, forbidden, forbidden, forbidden)
    assert await hooks.acquire_token("scope") is None
    assert await hooks.register_work_iq("scope") is None
    await hooks.notify_pending("SAR1")


@pytest.mark.asyncio
async def test_actual_kyc_agent_integration(cfg):
    if importlib.util.find_spec("kyc_agent") is None:
        pytest.skip("Concurrent kyc_agent component is not installed yet")
    reply = await KycHandler(cfg).handle("Screen customer CUST-1003", "integration", "Workshop Analyst")
    assert reply.text and reply.risk is not None and reply.sar is not None
    assert summary_card(reply)["type"] == "AdaptiveCard"

@pytest.mark.asyncio
async def test_agent_cannot_preapprove_new_sar(cfg):
    class PreapprovedAgent(StubAgent):
        async def run(self, *args):
            reply = await super().run(*args)
            return reply.model_copy(update={"sar": reply.sar.model_copy(update={"status": "approved", "approved_by": "auto-policy"})})
    reply = await KycHandler(cfg, PreapprovedAgent()).handle("screen", "c", "a")
    assert reply.sar.status == "pending_approval" and reply.sar.approved_by is None


@pytest.mark.asyncio
async def test_invalid_payload(cfg):
    with pytest.raises(ValueError, match="payload"):
        await KycHandler(cfg, StubAgent()).handle("", "c", "a", "invalid")


@pytest.mark.asyncio
async def test_optional_a365_scope_uses_installed_sdk(cfg):
    from importlib.util import find_spec
    try:
        installed = find_spec("microsoft_agents_a365.observability.core")
    except ModuleNotFoundError:
        installed = None
    if not installed:
        pytest.skip("Optional Agent365 SDK not installed")
    hooks = A365Integration(cfg)
    from microsoft_agents_a365.observability import core
    hooks.core = core
    with hooks.scope("agent", "test.invoke", "synthetic") as invocation:
        assert isinstance(invocation, core.InvokeAgentScope)
        with hooks.scope("tool", "test.tool") as tool:
            assert isinstance(tool, core.ExecuteToolScope)

@pytest.mark.asyncio
async def test_live_http_requires_auth(cfg, monkeypatch):
    monkeypatch.setenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__AUTHTYPE", "ClientSecret")
    monkeypatch.setenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID", "11111111-1111-4111-8111-111111111111")
    monkeypatch.setenv("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID", "22222222-2222-4222-8222-222222222222")
    # No credential acquisition occurs: reject before the adapter/agent is reached.
    live = replace(cfg, demo_mode="live")
    async with TestClient(TestServer(create_app(live, KycHandler(live, StubAgent())))) as client:
        assert (await client.get("/healthz")).status == 200
        assert (await client.post("/api/messages", json=activity())).status == 401

@pytest.mark.asyncio
async def test_live_hooks_require_explicit_identity_and_tool_policy(cfg):
    calls = []
    async def token(scope):
        calls.append(("token", scope))
        return "synthetic-test-token"
    async def register(bearer):
        calls.append(("register", bearer))
        return ["mail"]
    async def mail(sar_id):
        calls.append(("mail", sar_id))
    live = replace(cfg, demo_mode="live")
    hooks = A365Integration(live, token, register, mail)
    assert await hooks.register_work_iq("configured-resource/.default") == ["mail"]
    with pytest.raises(PermissionError):
        await hooks.notify_pending("SAR1")
    assert not any(call[0] == "mail" for call in calls)
    hooks = A365Integration(replace(live, allowed_tools=live.allowed_tools + ("notify_compliance",)), token, register, mail)
    await hooks.notify_pending("SAR1")
    assert calls[-1] == ("mail", "SAR1")
    assert AuditLog(cfg=cfg).read()[-1]["event"] == "compliance_notified"
    with pytest.raises(RuntimeError, match="token_provider"):
        await A365Integration(live).acquire_token("scope")
