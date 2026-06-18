from ninja import Router, Schema
from django.http import StreamingHttpResponse
from apps.chat.models import ChatSession, ChatMessage
from apps.chat.sse import sse_event_stream
from apps.tenants.auth import tenant_key_auth

chat_router = Router(tags=["chat"])


class MessageIn(Schema):
    session_id: str
    content: str


class IdentityIn(Schema):
    visitor_id: str


@chat_router.post("/identity", auth=tenant_key_auth)
def issue_identity_hash(request, body: IdentityIn):
    """TENANT_KEY 인증으로 visitor_id의 검증 해시를 발급한다(유저당 1회, 캐시 가능)."""
    from apps.chat.identity import compute_identity_hash

    tenant = request.auth
    return {
        "visitor_id": body.visitor_id,
        "hash": compute_identity_hash(str(tenant.id), body.visitor_id),
    }


@chat_router.get("/stream")
def stream(request, slug: str, visitor_id: str = "", hash: str = ""):
    from apps.tenants.models import Tenant

    tenant = Tenant.resolve_slug(slug)
    if not tenant:
        return StreamingHttpResponse(status=404)
    if not visitor_id:
        return StreamingHttpResponse(status=400)

    # 신원검증 토글이 켜진 Tenant는 유효한 HMAC 해시가 있어야 visitor_id 위조를 막는다.
    config = getattr(tenant, "config", None)
    if config and config.require_identity_verification:
        from apps.chat.identity import verify_identity
        if not verify_identity(str(tenant.id), visitor_id, hash):
            return StreamingHttpResponse(status=401)

    session, _ = ChatSession.objects.get_or_create(
        tenant_id=tenant.id,
        visitor_id=visitor_id,
        ended_at=None,
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
        from apps.chat.tasks import run_chat_agent_task
        run_chat_agent_task.delay(str(session.id), body.content)

    return 202, {"status": "processing"}
