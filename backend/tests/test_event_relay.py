"""relay 드레인 (issue 144). 순서·prune·실패 재발행·sweep을 검증.

happy-path는 실 Redis Streams로, 발행 실패 주입은 controllable fake bus로(실 Redis는 결정적
실패를 못 만들므로 — relay 로직 검증이 관심사, bus 자체는 142에서 검증됨).
"""
import uuid
import pytest


def _topic():
    return f"test.relay.{uuid.uuid4().hex}"


@pytest.mark.django_db
def test_drains_in_order_prunes_outbox_keeps_event_store():
    from apps.events.store import record_event
    from apps.events.relay import drain_once
    from apps.events.models import Outbox, EventStore
    from apps.events.bus import RedisStreamsBus

    topic = _topic()
    bus = RedisStreamsBus()
    bus.ensure_group(topic, "g")
    for i in range(3):
        record_event("E", f"s{i}", "t", {"i": i}, topic=topic)

    n = drain_once(bus)

    assert n == 3
    assert Outbox.objects.filter(published_at__isnull=True).count() == 0  # 발행분 prune
    assert EventStore.objects.count() == 3                                # 감사 불변
    msgs = bus.consume(topic, "g", "c", count=10, block_ms=300)
    assert [m.payload["payload"]["i"] for m in msgs] == [0, 1, 2]         # id 순서


class _OkBus:
    def __init__(self):
        self.published = []

    def publish(self, topic, key, payload):
        self.published.append(payload["payload"]["i"])


class _FlakyBus(_OkBus):
    def __init__(self, fail_on):
        super().__init__()
        self.calls = 0
        self.fail_on = fail_on

    def publish(self, topic, key, payload):
        self.calls += 1
        if self.calls == self.fail_on:
            raise RuntimeError("publish boom")
        super().publish(topic, key, payload)


@pytest.mark.django_db
def test_failed_publish_leaves_remaining_unpublished_and_retries():
    from apps.events.store import record_event
    from apps.events.relay import drain_once
    from apps.events.models import Outbox

    topic = _topic()
    for i in range(3):
        record_event("E", f"s{i}", "t", {"i": i}, topic=topic)

    flaky = _FlakyBus(fail_on=2)
    with pytest.raises(RuntimeError):
        drain_once(flaky)

    assert flaky.published == [0]                                          # 1건만 발행
    assert Outbox.objects.filter(published_at__isnull=True).count() == 2   # 나머지 미발행 유지

    ok = _OkBus()
    drain_once(ok)  # sweep/재시도
    assert ok.published == [1, 2]                                          # 남은 것 순서대로 재발행
    assert Outbox.objects.filter(published_at__isnull=True).count() == 0
