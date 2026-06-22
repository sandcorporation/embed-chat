"""visitor-bridge 소비자 (issue 147). 실 Redis: session:{id} 채널 구독으로 검증."""
import json
import uuid
import pytest


def _bus():
    from apps.events.bus import RedisStreamsBus
    return RedisStreamsBus()


def _env(event_type, session_id):
    return {
        "event_id": str(uuid.uuid4()), "type": event_type, "aggregate_id": str(session_id),
        "tenant_id": "t", "occurred_at": "2026-06-22T00:00:00+00:00", "schema_version": 1, "payload": {},
    }


def _read_event(pubsub, want_type, tries=20):
    for _ in range(tries):
        msg = pubsub.get_message(timeout=0.5)
        if msg and msg["type"] == "message" and json.loads(msg["data"]).get("type") == want_type:
            return True
    return False


def _run(bus, topic, env):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.visitor_bridge import handle
    bus.ensure_group(topic, "visitor-bridge")
    bus.publish(topic, key=env["aggregate_id"], payload=env)
    EventConsumer(bus, topic, "visitor-bridge", "c", handle).process_once(block_ms=300)


@pytest.mark.django_db
def test_escalated_publishes_hitl_start(redis_subscribe):
    from apps.events.types import SESSION_ESCALATED
    bus, topic, sid = _bus(), f"test.vb.{uuid.uuid4().hex}", f"s-{uuid.uuid4().hex}"
    pubsub = redis_subscribe(f"session:{sid}")
    _run(bus, topic, _env(SESSION_ESCALATED, sid))
    assert _read_event(pubsub, "hitl_start")


@pytest.mark.django_db
def test_taken_over_publishes_hitl_start(redis_subscribe):
    from apps.events.types import SESSION_TAKEN_OVER
    bus, topic, sid = _bus(), f"test.vb.{uuid.uuid4().hex}", f"s-{uuid.uuid4().hex}"
    pubsub = redis_subscribe(f"session:{sid}")
    _run(bus, topic, _env(SESSION_TAKEN_OVER, sid))
    assert _read_event(pubsub, "hitl_start")


@pytest.mark.django_db
def test_resolved_publishes_hitl_end(redis_subscribe):
    from apps.events.types import ESCALATION_RESOLVED
    bus, topic, sid = _bus(), f"test.vb.{uuid.uuid4().hex}", f"s-{uuid.uuid4().hex}"
    pubsub = redis_subscribe(f"session:{sid}")
    _run(bus, topic, _env(ESCALATION_RESOLVED, sid))
    assert _read_event(pubsub, "hitl_end")
