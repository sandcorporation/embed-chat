"""record_event — 상태 전이와 같은 트랜잭션에서 도메인 이벤트를 기록한다 (issue 143).

event_store(영구 감사)와 outbox(전송 큐)에 둘 다 insert한다. 호출자의 transaction.atomic
안에서 부르면 상태 변경과 원자적이라, 커밋되면 둘 다, 롤백되면 둘 다 안 남는다(dual-write 제거).
"""
import uuid
from django.conf import settings
from django.db import transaction
from django.utils import timezone


def default_topic() -> str:
    # v1: HITL/세션 라이프사이클은 단일 글로벌 내구 스트림(settings.EVENTS_TOPIC, 테스트는 격리).
    return settings.EVENTS_TOPIC


def record_event(event_type, aggregate_id, tenant_id, payload=None, *,
                 topic=None, key=None, schema_version=1):
    """도메인 이벤트를 event_store + outbox에 기록하고 봉투(dict)를 반환한다."""
    from apps.events.models import EventStore, Outbox

    topic = topic or default_topic()
    now = timezone.now()
    event_id = uuid.uuid4()
    envelope = {
        "event_id": str(event_id),
        "type": event_type,
        "aggregate_id": str(aggregate_id),
        "tenant_id": str(tenant_id),
        "occurred_at": now.isoformat(),
        "schema_version": schema_version,
        "payload": payload or {},
    }
    EventStore.objects.create(
        event_id=event_id, type=event_type, aggregate_id=str(aggregate_id),
        tenant_id=str(tenant_id), occurred_at=now, schema_version=schema_version,
        payload=payload or {},
    )
    Outbox.objects.create(
        event_id=event_id, topic=topic, key=str(key or aggregate_id), envelope=envelope,
    )
    # relay wake는 반드시 커밋 후에 발행한다 — 그래야 relay가 깨서 outbox를 조회할 때 이 행이
    # 보인다(롤백되면 wake도 안 나감). 정합성은 outbox+relay sweep이 보장, wake는 저지연 신호.
    from apps.events.wake import notify_outbox
    transaction.on_commit(notify_outbox)
    return envelope
