from typing import List
from apps.memory.models import VisitorMemory


def get_visitor_memories(tenant_id: str, visitor_id: str) -> List[str]:
    memories = VisitorMemory.objects.filter(tenant_id=tenant_id, visitor_id=visitor_id)
    return [f"{m.key}: {m.value}" for m in memories]


def upsert_memory(tenant_id: str, visitor_id: str, key: str, value: str) -> VisitorMemory:
    memory, _ = VisitorMemory.objects.update_or_create(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        key=key,
        defaults={"value": value},
    )
    return memory


def delete_memory(tenant_id: str, visitor_id: str, memory_id: str) -> bool:
    deleted, _ = VisitorMemory.objects.filter(
        id=memory_id,
        tenant_id=tenant_id,
        visitor_id=visitor_id,
    ).delete()
    return deleted > 0
