from typing import List
from django.utils import timezone
from ninja import Router, Schema
from django.http import StreamingHttpResponse

from apps.tenants.auth import tenant_agent_auth
from apps.chat.sse import publish_hitl_message
from apps.events.store import record_event
from apps.events.types import ESCALATION_CLAIMED, ESCALATION_RESOLVED

escalation_router = Router(tags=["escalations"], auth=tenant_agent_auth)


class MessageIn(Schema):
    content: str


class EscalationOut(Schema):
    id: str
    session_id: str
    trigger_type: str
    reason: str
    status: str
    created_at: str


class EscalationMessageOut(Schema):
    id: str
    role: str
    content: str
    created_at: str


class ActionOut(Schema):
    status: str


class DetailOut(Schema):
    detail: str


@escalation_router.get("/", response=List[EscalationOut])
def list_escalations(request):
    from apps.escalation.models import Escalation

    tenant = request.auth.tenant
    escalations = (
        Escalation.objects.filter(
            session__tenant_id=tenant.id,
            status__in=[Escalation.STATUS_PENDING, Escalation.STATUS_CLAIMED],
        )
        .select_related("session")
        .order_by("-created_at")
    )

    return [
        {
            "id": str(e.id),
            "session_id": str(e.session_id),
            "trigger_type": e.trigger_type,
            "reason": e.reason,
            "status": e.status,
            "created_at": e.created_at.isoformat(),
        }
        for e in escalations
    ]


@escalation_router.post("/{escalation_id}/claim", response={200: ActionOut, 404: DetailOut, 409: DetailOut})
def claim_escalation(request, escalation_id: str):
    from apps.escalation.models import Escalation, EscalationClaim
    from django.db import IntegrityError, transaction

    tenant = request.auth.tenant
    try:
        esc = Escalation.objects.get(id=escalation_id, session__tenant_id=tenant.id)
    except Escalation.DoesNotExist:
        return 404, {"detail": "Not found"}

    try:
        with transaction.atomic():
            EscalationClaim.objects.create(escalation=esc, claimed_by=request.auth.username)
            esc.status = Escalation.STATUS_CLAIMED
            esc.save(update_fields=["status"])
            # 콘솔 델타는 EscalationClaimed 이벤트의 console-bridge 소비자가 발행한다(issue 151).
            record_event(
                ESCALATION_CLAIMED, aggregate_id=str(esc.session_id), tenant_id=str(tenant.id),
                payload={"escalation_id": str(esc.id), "claimed_by": request.auth.username},
            )
    except IntegrityError:
        return 409, {"detail": "Already claimed"}

    return {"status": "claimed"}


@escalation_router.post("/{escalation_id}/message", response={200: ActionOut, 404: DetailOut})
def send_message(request, escalation_id: str, body: MessageIn):
    from apps.escalation.models import Escalation
    from apps.chat.models import ChatMessage

    tenant = request.auth.tenant
    try:
        esc = Escalation.objects.select_related("session").get(
            id=escalation_id, session__tenant_id=tenant.id
        )
    except Escalation.DoesNotExist:
        return 404, {"detail": "Not found"}

    from apps.tenants.models import TenantConfig
    config = TenantConfig.objects.get(tenant_id=esc.session.tenant_id)

    ChatMessage.objects.create(
        session=esc.session,
        role=ChatMessage.ROLE_HUMAN_AGENT,
        content=body.content,
    )
    publish_hitl_message(str(esc.session_id), body.content, config.agent_display_name)

    return {"status": "sent"}


@escalation_router.get("/{escalation_id}/messages", response={200: List[EscalationMessageOut], 404: DetailOut})
def get_escalation_messages(request, escalation_id: str):
    from apps.escalation.models import Escalation
    from apps.chat.models import ChatMessage

    tenant = request.auth.tenant
    try:
        esc = Escalation.objects.select_related("session").get(
            id=escalation_id, session__tenant_id=tenant.id
        )
    except Escalation.DoesNotExist:
        return 404, {"detail": "Not found"}

    messages = ChatMessage.objects.filter(session=esc.session).order_by("created_at")
    return 200, [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@escalation_router.post("/{escalation_id}/typing", response={200: ActionOut, 404: DetailOut})
def send_typing_indicator(request, escalation_id: str):
    from apps.escalation.models import Escalation
    from apps.chat.sse import get_redis_client
    import json

    tenant = request.auth.tenant
    try:
        esc = Escalation.objects.select_related("session").get(
            id=escalation_id, session__tenant_id=tenant.id
        )
    except Escalation.DoesNotExist:
        return 404, {"detail": "Not found"}

    r = get_redis_client()
    r.publish(
        f"session:{esc.session_id}",
        json.dumps({"type": "typing", "actor": "human_agent"}),
    )
    return 200, {"status": "ok"}


@escalation_router.post("/{escalation_id}/resolve", response={200: ActionOut, 404: DetailOut})
def resolve_escalation(request, escalation_id: str):
    from apps.escalation.models import Escalation
    from django.db import transaction

    tenant = request.auth.tenant
    try:
        esc = Escalation.objects.select_related("session").get(
            id=escalation_id, session__tenant_id=tenant.id
        )
    except Escalation.DoesNotExist:
        return 404, {"detail": "Not found"}

    with transaction.atomic():
        esc.status = Escalation.STATUS_RESOLVED
        esc.resolved_at = timezone.now()
        esc.save(update_fields=["status", "resolved_at"])
        session = esc.session
        session.is_hitl = False
        session.save(update_fields=["is_hitl"])
        # 방문자 hitl_end는 EscalationResolved 이벤트의 visitor-bridge 소비자가 발행한다(issue 151).
        record_event(
            ESCALATION_RESOLVED, aggregate_id=str(session.id), tenant_id=str(tenant.id),
            payload={"escalation_id": str(esc.id)},
        )

    return {"status": "resolved"}


@escalation_router.get("/stream", auth=None)
def escalation_stream(request, token: str):
    from apps.chat.sse import get_redis_client
    from apps.tenants.auth import verify_tenant_agent_token
    from apps.tenants.models import TenantAgent
    import json

    payload = verify_tenant_agent_token(token)
    if not payload:
        from django.http import HttpResponse
        return HttpResponse(status=401)
    try:
        agent = TenantAgent.objects.select_related("tenant").get(
            id=payload["sub"], is_active=True
        )
    except TenantAgent.DoesNotExist:
        from django.http import HttpResponse
        return HttpResponse(status=401)

    channel = f"hitl:{agent.tenant_id}"

    def _event_generator():
        r = get_redis_client()
        pubsub = r.pubsub()
        pubsub.subscribe(channel)
        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield f"event: {data.get('type', 'message')}\ndata: {json.dumps(data)}\n\n"
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    response = StreamingHttpResponse(_event_generator(), content_type="text/event-stream")  # pyright: ignore[reportArgumentType]
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
