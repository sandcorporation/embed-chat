"""ephemeral 신호 발행 (issue 150).

presence 같은 휘발성 전이는 outbox·event_store를 거치지 않고(트랜잭션 상태가 아님) 곧바로
EventBus의 capped 스트림으로 발행한다. 같은 EventBus 포트를 쓰되 내구 경로와 분리된다(PRD).
"""
import uuid

from django.utils import timezone

from apps.events.types import PRESENCE_TOPIC

PRESENCE_MAXLEN = 10000  # capped — 휘발성이라 오래된 신호는 트림


def publish_presence(event_type: str, tenant_id: str, session_id: str, bus=None) -> None:
    from apps.events.bus import RedisStreamsBus

    bus = bus or RedisStreamsBus()
    envelope = {
        "event_id": str(uuid.uuid4()),
        "type": event_type,
        "aggregate_id": str(session_id),
        "tenant_id": str(tenant_id),
        "occurred_at": timezone.now().isoformat(),
        "schema_version": 1,
        "payload": {},
    }
    bus.publish(PRESENCE_TOPIC, key=str(session_id), payload=envelope, maxlen=PRESENCE_MAXLEN)
