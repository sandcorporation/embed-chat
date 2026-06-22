"""webhook 소비자 (issue 146). 실 Redis + 실 HTTP 수신 서버. 이벤트는 버스에 주입."""
import uuid
import pytest


def _bus():
    from apps.events.bus import RedisStreamsBus
    return RedisStreamsBus()


def _escalated_envelope(session_id, tenant_id, escalation_id, event_id=None):
    from apps.events.types import SESSION_ESCALATED
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "type": SESSION_ESCALATED,
        "aggregate_id": str(session_id),
        "tenant_id": str(tenant_id),
        "occurred_at": "2026-06-22T00:00:00+00:00",
        "schema_version": 1,
        "payload": {"escalation_id": str(escalation_id)},
    }


def _setup_escalation(tenant, webhook_url, webhook_type="generic"):
    from apps.tenants.models import TenantConfig
    from apps.chat.models import ChatSession
    from apps.escalation.models import Escalation
    config = TenantConfig.objects.get(tenant=tenant)
    config.webhook_url = webhook_url
    config.webhook_type = webhook_type
    config.save()
    sess = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v-wh")
    esc = Escalation.objects.create(session=sess, trigger_type="ai", status="pending", reason="도움 요청")
    return sess, esc


@pytest.mark.django_db
def test_webhook_fires_on_session_escalated(tenant_with_key, webhook_server):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.webhook import handle

    tenant, _ = tenant_with_key
    sess, esc = _setup_escalation(tenant, webhook_server["url"])

    bus, topic, group = _bus(), f"test.wh.{uuid.uuid4().hex}", "webhook"
    bus.ensure_group(topic, group)
    bus.publish(topic, key=str(sess.id), payload=_escalated_envelope(sess.id, tenant.id, esc.id))

    EventConsumer(bus, topic, group, "c", handle).process_once(block_ms=300)

    assert len(webhook_server["received"]) == 1
    assert webhook_server["received"][0]["data"]["reason"] == "도움 요청"


@pytest.mark.django_db
def test_webhook_idempotent_on_redelivery(tenant_with_key, webhook_server):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.webhook import handle

    tenant, _ = tenant_with_key
    sess, esc = _setup_escalation(tenant, webhook_server["url"])
    env = _escalated_envelope(sess.id, tenant.id, esc.id)

    bus, topic, group = _bus(), f"test.wh.{uuid.uuid4().hex}", "webhook"
    bus.ensure_group(topic, group)
    ec = EventConsumer(bus, topic, group, "c", handle)
    bus.publish(topic, key=str(sess.id), payload=env)
    ec.process_once(block_ms=300)
    bus.publish(topic, key=str(sess.id), payload=env)  # 같은 event_id 재전달
    ec.process_once(block_ms=300)

    assert len(webhook_server["received"]) == 1  # 이중발송 없음


@pytest.mark.django_db
def test_webhook_failure_dead_letters(tenant_with_key, failing_webhook_server):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.webhook import handle

    tenant, _ = tenant_with_key
    sess, esc = _setup_escalation(tenant, failing_webhook_server["url"])

    bus, topic, group = _bus(), f"test.wh.{uuid.uuid4().hex}", "webhook"
    bus.ensure_group(topic, group)
    bus.publish(topic, key=str(sess.id), payload=_escalated_envelope(sess.id, tenant.id, esc.id))

    EventConsumer(bus, topic, group, "c", handle, max_attempts=2).process_once(block_ms=300)

    assert len(bus.dead_letter_items(topic)) == 1  # 실패 → DLQ


@pytest.mark.django_db
def test_webhook_noop_when_unconfigured(tenant_with_key, webhook_server):
    from apps.events.consumer import EventConsumer
    from apps.events.handlers.webhook import handle

    tenant, _ = tenant_with_key
    sess, esc = _setup_escalation(tenant, webhook_url="", webhook_type="")  # 미설정

    bus, topic, group = _bus(), f"test.wh.{uuid.uuid4().hex}", "webhook"
    bus.ensure_group(topic, group)
    bus.publish(topic, key=str(sess.id), payload=_escalated_envelope(sess.id, tenant.id, esc.id))

    EventConsumer(bus, topic, group, "c", handle).process_once(block_ms=300)

    assert len(webhook_server["received"]) == 0  # no-op
    assert len(bus.dead_letter_items(topic)) == 0  # 실패 아님
