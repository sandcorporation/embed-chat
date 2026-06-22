"""presence-bridge 소비자 (issue 150). VisitorConnected/Disconnected → 콘솔 델타."""
import json
import uuid
import pytest


def _bus():
    from apps.events.bus import RedisStreamsBus
    return RedisStreamsBus()


def _env(event_type, tenant_id, session_id):
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


@pytest.mark.django_db
def test_presence_bridge_bridges_connect_and_disconnect(redis_subscribe):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.presence_bridge import handle
    from apps.events.types import VISITOR_CONNECTED, VISITOR_DISCONNECTED

    tenant_id, sid = f"t-{uuid.uuid4().hex}", f"s-{uuid.uuid4().hex}"
    pubsub = redis_subscribe(f"hitl:{tenant_id}")
    bus, topic, group = _bus(), f"test.pb.{uuid.uuid4().hex}", "presence-bridge"
    bus.ensure_group(topic, group)
    ec = EventConsumer(bus, topic, group, "c", handle)

    bus.publish(topic, key=sid, payload=_env(VISITOR_CONNECTED, tenant_id, sid))
    ec.process_once(block_ms=300)
    assert _read_event(pubsub, "session_connected")

    bus.publish(topic, key=sid, payload=_env(VISITOR_DISCONNECTED, tenant_id, sid))
    ec.process_once(block_ms=300)
    assert _read_event(pubsub, "session_disconnected")
