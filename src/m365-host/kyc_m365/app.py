from __future__ import annotations

import logging
import os

from aiohttp import web
from microsoft_agents.activity import Activity, ActivityTypes, Attachment, load_configuration_from_env
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import CloudAdapter, jwt_authorization_middleware, start_agent_process
from microsoft_agents.hosting.core import AgentApplication, AgentAuthConfiguration, ApplicationOptions, MemoryStorage

from kyc_core.config import Settings, settings
from .handlers import KycHandler, summary_card


@web.middleware
async def health_and_errors(request, handler):
    if request.path == "/healthz":
        return web.json_response({"status": "ok", "mode": request.app["cfg"].demo_mode})
    try:
        return await handler(request)
    except PermissionError as exc:
        return web.json_response({"error": str(exc)}, status=403)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)


def create_app(cfg: Settings | None = None, handler: KycHandler | None = None) -> web.Application:
    cfg = cfg or settings()
    handler = handler or KycHandler(cfg)
    if cfg.is_mock:
        # Ignore any workstation Entra credentials in mock mode.
        manager = None
        auth = AgentAuthConfiguration(anonymous_allowed=True)
    else:
        manager = MsalConnectionManager(**load_configuration_from_env(os.environ))
        auth = manager.get_default_connection_configuration()
        if auth.ANONYMOUS_ALLOWED or not auth.CLIENT_ID:
            raise ValueError("Live mode requires an authenticated service connection")
    adapter = CloudAdapter(connection_manager=manager)
    agent_app = AgentApplication(options=ApplicationOptions(adapter=adapter, storage=MemoryStorage(),
                                 start_typing_timer=False), connection_manager=manager)

    @agent_app.conversation_update("membersAdded")
    async def welcome(context, _state):
        recipient = context.activity.recipient
        if any(member.id != (recipient.id if recipient else None)
               for member in (context.activity.members_added or [])):
            await context.send_activity("Welcome to the KYC/AML compliance workshop. Ask to screen a synthetic customer. SARs require human review.")

    @agent_app.activity(ActivityTypes.message)
    async def message(context, _state):
        activity = context.activity
        sender = activity.from_property
        channel_data = activity.channel_data or {}
        tenant_id = channel_data.get("tenant", {}).get("id", "")
        try:
            reply = await handler.handle(activity.text or "", activity.conversation.id,
                sender.name or "", activity.value,
                tenant_id=tenant_id, user_id=sender.aad_object_id or sender.id or "")
        except (ValueError, PermissionError) as exc:
            await context.send_activity(str(exc))
            return
        await context.send_activity(reply.text)
        await context.send_activity(Activity(type=ActivityTypes.message, attachments=[Attachment(
            content_type="application/vnd.microsoft.card.adaptive", content=summary_card(reply))]))

    async def messages(request):
        return await start_agent_process(request, agent_app, adapter)

    app = web.Application(middlewares=[health_and_errors, jwt_authorization_middleware], client_max_size=1024 * 1024)
    app["cfg"], app["agent_configuration"], app["agent_application"], app["adapter"] = cfg, auth, agent_app, adapter
    async def health(_request):
        return web.json_response({"status": "ok", "mode": cfg.demo_mode})
    app.router.add_get("/healthz", health)
    app.router.add_post("/api/messages", messages)
    return app


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    cfg = settings()
    # Anonymous mock hosting must not be exposed publicly. Live is container-accessible.
    web.run_app(create_app(cfg), host=os.getenv("HOST", "127.0.0.1" if cfg.is_mock else "0.0.0.0"),
                port=int(os.getenv("PORT", "3978")))


if __name__ == "__main__":
    main()

