"""relay / consume_events management command 배선 (issue 149).

커맨드가 핸들러 레지스트리·relay·소비자를 올바로 엮는지 실 인프라로 검증.
"""
import uuid
import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_relay_once_drains_outbox():
    from apps.events.store import record_event
    from apps.events.models import Outbox
    from apps.events.bus import RedisStreamsBus

    topic = f"test.cmd.relay.{uuid.uuid4().hex}"
    RedisStreamsBus().ensure_group(topic, "g")
    record_event("E", "s1", "t", {"i": 1}, topic=topic)
    assert Outbox.objects.filter(published_at__isnull=True).count() == 1

    call_command("relay", "--once")

    assert Outbox.objects.filter(published_at__isnull=True).count() == 0  # 드레인됨


@pytest.mark.django_db
def test_consume_events_command_runs_registered_handler(tenant_with_key, webhook_server):
    from apps.tenants.models import TenantConfig
    from apps.chat.models import ChatSession
    from apps.escalation.models import Escalation
    from apps.events.bus import RedisStreamsBus
    from apps.events.types import SESSION_ESCALATED

    tenant, _ = tenant_with_key
    config = TenantConfig.objects.get(tenant=tenant)
    config.webhook_url, config.webhook_type = webhook_server["url"], "generic"
    config.save()
    sess = ChatSession.objects.create(tenant_id=tenant.id, visitor_id="v")
    esc = Escalation.objects.create(session=sess, trigger_type="ai", status="pending", reason="r")

    topic = f"test.cmd.consume.{uuid.uuid4().hex}"
    bus = RedisStreamsBus()
    bus.ensure_group(topic, "webhook")
    bus.publish(topic, key=str(sess.id), payload={
        "event_id": str(uuid.uuid4()), "type": SESSION_ESCALATED, "aggregate_id": str(sess.id),
        "tenant_id": str(tenant.id), "occurred_at": "2026-06-22T00:00:00+00:00",
        "schema_version": 1, "payload": {"escalation_id": str(esc.id)},
    })

    call_command("consume_events", "--group=webhook", "--once", f"--topic={topic}")

    assert len(webhook_server["received"]) == 1  # 커맨드→레지스트리→소비자→webhook 핸들러
