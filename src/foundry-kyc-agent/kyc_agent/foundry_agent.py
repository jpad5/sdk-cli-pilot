"""Live agent on Microsoft Foundry Agent Service (azure-ai-projects 2.x).

The model plans; tools run locally inside this process so the governance
allow-list, audit log and human-in-the-loop SAR gate are always enforced.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlparse

from kyc_core.config import Settings, settings
from kyc_core.models import AgentReply, KycDecision
from kyc_core.telemetry import current_trace_id, span

from . import tools, workflow

INSTRUCTIONS = """You are a KYC/AML onboarding analyst for Contoso Bank (synthetic workshop data only).
For every onboarding or screening request:
1. Call lookup_customer, then screen_name with the customer's name, date of birth and country.
2. Call assess_customer to get the rule-based risk score and decision.
3. Explain the decision citing the screening sources checked and each risk factor.
Rules: never invent screening results; never state that a SAR has been filed - SARs always
require a named human approver; if a customer cannot be found, ask for a customer ID like CUST-1001."""

FUNCTION_SPECS: list[dict[str, Any]] = [
    {"name": "lookup_customer", "description": "Look up a synthetic customer profile by id (CUST-1001) or full name.",
     "parameters": {"type": "object", "properties": {"customer_id_or_name": {"type": "string"}},
                    "required": ["customer_id_or_name"], "additionalProperties": False}},
    {"name": "screen_name", "description": "Screen a name against synthetic sanctions, PEP and adverse-media lists.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "dob": {"type": ["string", "null"]},
                                                       "country": {"type": ["string", "null"]}},
                    "required": ["name", "dob", "country"], "additionalProperties": False}},
    {"name": "assess_customer", "description": "Run rule-based risk scoring and the KYC decision policy; drafts a SAR "
                                               "for human approval when required.",
     "parameters": {"type": "object", "properties": {"customer_id_or_name": {"type": "string"}},
                    "required": ["customer_id_or_name"], "additionalProperties": False}},
]


class FoundryKycAgent:
    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or settings()
        if not self.cfg.foundry_project_endpoint:
            raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is required in live mode (run `azd provision` or set .env)")
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        self.project = AIProjectClient(endpoint=self.cfg.foundry_project_endpoint, credential=DefaultAzureCredential())
        self.openai = self.project.get_openai_client()
        self._conversations: dict[str, str] = {}

    def build_tools(self) -> list[Any]:
        from azure.ai.projects.models import FunctionTool, MCPTool

        defs: list[Any] = [FunctionTool(name=s["name"], description=s["description"], parameters=s["parameters"],
                                        strict=True) for s in FUNCTION_SPECS]
        host = urlparse(self.cfg.mcp_sanctions_url).hostname or ""
        if host not in ("localhost", "127.0.0.1", ""):
            # Foundry calls MCP servers from the cloud, so only a publicly reachable endpoint is attached.
            defs.append(MCPTool(server_label="kyc-sanctions", server_url=self.cfg.mcp_sanctions_url,
                                require_approval="never", allowed_tools=["list_sources"]))
        return defs

    def deploy(self) -> Any:
        from azure.ai.projects.models import PromptAgentDefinition

        with span("agent.deploy", **{"gen_ai.agent.name": self.cfg.foundry_agent_name}):
            return self.project.agents.create_version(
                agent_name=self.cfg.foundry_agent_name,
                definition=PromptAgentDefinition(model=self.cfg.foundry_model_deployment, instructions=INSTRUCTIONS,
                                                 tools=self.build_tools()),
                description="FSI KYC/AML onboarding agent (workshop)",
            )

    def _execute(self, name: str, args: dict[str, Any], state: dict[str, Any]) -> str:
        if name == "lookup_customer":
            profile = tools.lookup_customer(args["customer_id_or_name"], cfg=self.cfg)
            return profile.model_dump_json() if profile else json.dumps({"error": "not found"})
        if name == "screen_name":
            return tools.screen_name(args["name"], dob=args.get("dob"), country=args.get("country"),
                                     cfg=self.cfg).model_dump_json()
        if name == "assess_customer":
            reply = workflow.assess(args["customer_id_or_name"], self.cfg)
            state["assessment"] = reply
            return reply.model_dump_json(exclude={"text", "trace_id"})
        return json.dumps({"error": f"unknown tool {name}"})

    def _run_sync(self, message: str, conversation_id: str) -> AgentReply:
        if m := workflow.APPROVE.search(message):
            return workflow.approve(m.group(1), m.group(2), self.cfg)
        agent_ref = {"agent_reference": {"name": self.cfg.foundry_agent_name, "type": "agent_reference"}}
        conv = self._conversations.get(conversation_id)
        if conv is None:
            conv = self.openai.conversations.create().id
            self._conversations[conversation_id] = conv
        state: dict[str, Any] = {}
        calls: list[str] = []
        response = self.openai.responses.create(conversation=conv, input=message, extra_body=agent_ref)
        for _ in range(8):
            pending = [item for item in response.output if item.type == "function_call"]
            if not pending:
                break
            outputs = []
            for item in pending:
                calls.append(item.name)
                try:
                    out = self._execute(item.name, json.loads(item.arguments or "{}"), state)
                except PermissionError as exc:
                    out = json.dumps({"error": str(exc)})
                outputs.append({"type": "function_call_output", "call_id": item.call_id, "output": out})
            response = self.openai.responses.create(conversation=conv, input=outputs, extra_body=agent_ref)
        assessed: AgentReply | None = state.get("assessment")
        return AgentReply(
            text=response.output_text,
            decision=assessed.decision if assessed else None,
            risk=assessed.risk if assessed else None,
            screening=assessed.screening if assessed else None,
            sar=assessed.sar if assessed else None,
            tool_calls=calls,
            trace_id=current_trace_id(),
        )

    async def run(self, message: str, conversation_id: str, user: str) -> AgentReply:
        with span("agent.invoke", **{"gen_ai.agent.name": self.cfg.foundry_agent_name, "kyc.mode": "live",
                                      "kyc.conversation_id": conversation_id}):
            return await asyncio.to_thread(self._run_sync, message, conversation_id)


__all__ = ["FoundryKycAgent", "INSTRUCTIONS", "FUNCTION_SPECS", "KycDecision"]
