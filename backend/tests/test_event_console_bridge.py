"""console-bridge 소비자 (issue 148). 실 Redis: hitl:{tenant} 채널 구독으로 검증."""
import json
import uuid
import pytest


def _bus():
    from apps.events.bus import RedisStreamsBus
    return RedisStreamsBus()


def _env(event_type, tenant_id, session_id="s1"):
    return {
        "event_id": str(uuid.uuid4()), "type": event_type, "aggregate_id": str(session_id),
        "tenant_id": str(tenant_id), "occurred_at": "2026-06-22T00:00:00+00:00",
        "schema_version": 1, "payload": {},
    }


def _read_event(pubsub, want_type, tries=20):
    for _ in range(tries):
        msg = pubsub.get_message(timeout=0.5)
        if msg and msg["type"] == "message" and json.loads(msg["data"]).get("type") == want_type:
            return True
    return False


def _run(bus, topic, env):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.console_bridge import handle
    bus.ensure_group(topic, "console-bridge")
    bus.publish(topic, key=env["aggregate_id"], payload=env)
    EventConsumer(bus, topic, "console-bridge", "c", handle).process_once(block_ms=300)


@pytest.mark.django_db
@pytest.mark.parametrize("event_type,delta", [
    ("SessionEscalated", "hitl_new"),
    ("SessionTakenOver", "hitl_new"),
    ("EscalationClaimed", "hitl_claimed"),
    ("EscalationResolved", "hitl_resolved"),
])
def test_lifecycle_event_publishes_console_delta(redis_subscribe, event_type, delta):
    tenant_id = f"t-{uuid.uuid4().hex}"
    bus, topic = _bus(), f"test.cb.{uuid.uuid4().hex}"
    pubsub = redis_subscribe(f"hitl:{tenant_id}")
    _run(bus, topic, _env(event_type, tenant_id))
    assert _read_event(pubsub, delta)
