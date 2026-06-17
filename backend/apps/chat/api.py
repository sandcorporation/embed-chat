import threading
from ninja import Router, Schema
from django.http import StreamingHttpResponse
from apps.chat.embed_token import create_embed_token, verify_embed_token
from apps.chat.models import ChatSession, ChatMessage
from apps.chat.sse import sse_event_stream
from apps.tenants.auth import tenant_key_auth

embed_router = Router(tags=["embed"])
chat_router = Router(tags=["chat"])


class EmbedTokenIn(Schema):
    visitor_id: str
    visitor_context: dict = {}


class EmbedTokenOut(Schema):
    embed_token: str


class MessageIn(Schema):
    session_id: str
    content: str


@embed_router.post("/token", response={200: EmbedTokenOut}, auth=tenant_key_auth)
def issue_embed_token(request, body: EmbedTokenIn):
    tenant = request.auth
    token = create_embed_token(
        tenant_id=str(tenant.id),
        visitor_id=body.visitor_id,
        visitor_context=body.visitor_context,
    )
    return {"embed_token": token}


@chat_router.get("/stream")
def stream(request, token: str):
    payload = verify_embed_token(token)
    if not payload:
        return StreamingHttpResponse(status=401)

    from apps.tenants.models import Tenant
    try:
        tenant = Tenant.objects.get(id=payload["tenant_id"], is_active=True)
    except Tenant.DoesNotExist:
        return StreamingHttpResponse(status=401)

    session, _ = ChatSession.objects.get_or_create(
        tenant_id=payload["tenant_id"],
        visitor_id=payload["visitor_id"],
        ended_at=None,
        defaults={"visitor_context": payload.get("visitor_context", {})},
    )

    existing_messages = ChatMessage.objects.filter(session=session).order_by("created_at")
    if existing_messages.exists():
        history = [{"role": m.role, "content": m.content} for m in existing_messages]
        stream_kwargs = {"history": history, "is_hitl": session.is_hitl}
    else:
        welcome_message = tenant.config.welcome_message if hasattr(tenant, "config") else ""
        stream_kwargs = {"welcome_message": welcome_message}

    response = StreamingHttpResponse(
        sse_event_stream(str(session.id), **stream_kwargs),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["X-Session-Id"] = str(session.id)
    return response


@chat_router.post("/message", response={202: dict, 404: dict})
def send_message(request, body: MessageIn):
    try:
        session = ChatSession.objects.get(id=body.session_id, ended_at=None)
    except ChatSession.DoesNotExist:
        return 404, {"detail": "Session not found"}

    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_USER,
        content=body.content,
    )

    if session.is_hitl:
        from apps.chat.sse import publish_visitor_message
        publish_visitor_message(str(session.tenant_id), str(session.id), body.content)
    else:
        thread = threading.Thread(
            target=_run_agent,
            args=(session, body.content),
            daemon=True,
        )
        thread.start()

    return 202, {"status": "processing"}


def _run_agent(session: ChatSession, user_message: str) -> None:
    from apps.agent.graph import run_chat_agent

    try:
        run_chat_agent(session, user_message)
    except Exception as e:
        from apps.chat.sse import publish_error
        publish_error(str(session.id), str(e))
