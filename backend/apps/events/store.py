"""record_event — 상태 전이와 같은 트랜잭션에서 도메인 이벤트를 기록한다 (issue 143).

event_store(영구 감사)와 outbox(전송 큐)에 둘 다 insert한다. 호출자의 transaction.atomic
안에서 부르면 상태 변경과 원자적이라, 커밋되면 둘 다, 롤백되면 둘 다 안 남는다(dual-write 제거).
"""
import uuid
from django.conf import settings
from django.db import connection
from django.utils import timezone

# relay가 LISTEN하는 NOTIFY 채널. pg_notify는 커밋 시 전달되므로 트랜잭션 원자성과 일치한다.
OUTBOX_NOTIFY_CHANNEL = "event_outbox"


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
    # relay를 깨운다. pg_notify는 COMMIT 시 전달되므로, 트랜잭션이 롤백되면 NOTIFY도 안 나간다.
    with connection.cursor() as cur:
        cur.execute("SELECT pg_notify(%s, %s)", [OUTBOX_NOTIFY_CHANNEL, str(event_id)])
    return envelope
