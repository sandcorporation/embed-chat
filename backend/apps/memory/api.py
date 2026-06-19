from typing import List, Optional
from ninja import Router, Schema
from django.shortcuts import get_object_or_404
from apps.tenants.auth import tenant_agent_auth
from apps.memory.models import VisitorMemory
from apps.memory.manager import upsert_memory, delete_memory

memory_router = Router(tags=["memory"], auth=tenant_agent_auth)
session_router = Router(tags=["sessions"], auth=tenant_agent_auth)


class DetailOut(Schema):
    detail: str


class SessionMessageOut(Schema):
    id: str
    role: str
    content: str
    created_at: str


class VisitorOut(Schema):
    visitor_id: str


class VisitorSessionOut(Schema):
    session_id: str
    visitor_id: str
    is_hitl: bool
    created_at: str


# checkpoint의 200 body는 LangGraph channel_values라 그래프 상태에 따라 구조가 달라지는
# 동적 맵이다 → 고정 Schema가 부적합하므로 dict로 유지(ADR-0014 와이어 불변). 404만 정형화.
@session_router.get("/{session_id}/checkpoint", response={200: dict, 404: DetailOut})
def get_session_checkpoint(request, session_id: str):
    from apps.chat.models import ChatSession
    from apps.agent.graph import _create_checkpointer

    tenant = request.auth.tenant
    try:
        ChatSession.objects.get(id=session_id, tenant_id=tenant.id)
    except ChatSession.DoesNotExist:
        return 404, {"detail": "Not found"}

    saver, conn = _create_checkpointer()
    try:
        checkpoint = saver.get({"configurable": {"thread_id": session_id}})
    finally:
        conn.close()

    if checkpoint is None:
        return 404, {"detail": "No checkpoint"}

    return 200, checkpoint.get("channel_values", {})


@session_router.get("/{session_id}/messages/", response={200: List[SessionMessageOut], 404: DetailOut})
def get_session_messages(request, session_id: str):
    from apps.chat.models import ChatSession, ChatMessage

    tenant = request.auth.tenant
    try:
        session = ChatSession.objects.get(id=session_id, tenant_id=tenant.id)
    except ChatSession.DoesNotExist:
        return 404, {"detail": "Not found"}

    messages = ChatMessage.objects.filter(session=session).order_by("created_at")
    return 200, [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@memory_router.get("/", response=List[VisitorOut])
def list_visitors(request, search: Optional[str] = None):
    from apps.chat.models import ChatSession

    tenant = request.auth.tenant
    qs = ChatSession.objects.filter(tenant_id=tenant.id)
    if search:
        qs = qs.filter(visitor_id__icontains=search)
    visitor_ids = list(qs.values_list("visitor_id", flat=True).distinct())
    return [{"visitor_id": vid} for vid in visitor_ids]


class MemoryOut(Schema):
    id: str
    key: str
    value: str


class MemoryIn(Schema):
    key: str
    value: str


@memory_router.get("/{visitor_id}/sessions/", response=List[VisitorSessionOut])
def list_visitor_sessions(request, visitor_id: str):
    from apps.chat.models import ChatSession

    tenant = request.auth.tenant
    sessions = ChatSession.objects.filter(
        tenant_id=tenant.id, visitor_id=visitor_id
    ).order_by("-created_at")
    return [
        {
            "session_id": str(s.id),
            "visitor_id": s.visitor_id,
            "is_hitl": s.is_hitl,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@memory_router.get("/{visitor_id}/memory/", response=List[MemoryOut])
def list_memories(request, visitor_id: str):
    tenant = request.auth.tenant
    memories = VisitorMemory.objects.filter(tenant_id=tenant.id, visitor_id=visitor_id)
    return [{"id": str(m.id), "key": m.key, "value": m.value} for m in memories]


@memory_router.patch("/{visitor_id}/memory/{memory_id}", response=MemoryOut)
def update_memory(request, visitor_id: str, memory_id: str, body: MemoryIn):
    tenant = request.auth.tenant
    memory = get_object_or_404(VisitorMemory, id=memory_id, tenant_id=tenant.id, visitor_id=visitor_id)
    memory.key = body.key
    memory.value = body.value
    memory.save()
    return {"id": str(memory.id), "key": memory.key, "value": memory.value}


@memory_router.delete("/{visitor_id}/memory/{memory_id}", response={204: None, 404: DetailOut})
def delete_memory_entry(request, visitor_id: str, memory_id: str):
    tenant = request.auth.tenant
    deleted = delete_memory(str(tenant.id), visitor_id, memory_id)
    if not deleted:
        return 404, {"detail": "Not found"}
    return 204, None
