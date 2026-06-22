"""event_store + outbox + record_event (issue 143). 실 Postgres로 검증."""
import pytest


@pytest.mark.django_db
def test_record_event_writes_store_and_outbox():
    from apps.events.store import record_event
    from apps.events.models import EventStore, Outbox

    env = record_event("SessionEscalated", aggregate_id="sess-1", tenant_id="ten-1",
                        payload={"reason": "도움 요청"})

    assert EventStore.objects.filter(event_id=env["event_id"]).count() == 1
    ob = Outbox.objects.get(event_id=env["event_id"])
    assert ob.published_at is None                      # 미발행
    assert ob.envelope["type"] == "SessionEscalated"
    assert ob.envelope["aggregate_id"] == "sess-1"
    assert ob.key == "sess-1"                           # 기본 key = aggregate_id
    assert ob.envelope["payload"]["reason"] == "도움 요청"


@pytest.mark.django_db
def test_record_event_is_atomic_with_caller_transaction():
    """호출자 트랜잭션이 롤백되면 event_store·outbox 둘 다 기록되지 않는다."""
    from django.db import transaction
    from apps.events.store import record_event
    from apps.events.models import EventStore, Outbox

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            record_event("X", "s", "t", {})
            raise RuntimeError("rollback")

    assert EventStore.objects.count() == 0
    assert Outbox.objects.count() == 0


@pytest.mark.django_db
def test_envelope_has_canonical_fields():
    from apps.events.store import record_event
    env = record_event("X", "s", "t", {"a": 1})
    for f in ("event_id", "type", "aggregate_id", "tenant_id", "occurred_at", "schema_version", "payload"):
        assert f in env
    assert env["schema_version"] == 1
