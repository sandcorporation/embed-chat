"""EventBus 포트 + Redis Streams 어댑터 (issue 142).

실 Redis Streams로 검증(CLAUDE.md: 결정적 인프라는 실객체). 테스트마다 유니크 topic으로 격리.
"""
import uuid


def _bus():
    from apps.events.bus import RedisStreamsBus
    return RedisStreamsBus()


def _topic():
    return f"test.events.{uuid.uuid4().hex}"


def test_publish_consume_ack_roundtrip():
    bus, topic, group = _bus(), _topic(), "g1"
    bus.ensure_group(topic, group)
    bus.publish(topic, key="s1", payload={"event_id": "e1", "type": "X"})

    msgs = bus.consume(topic, group, "c1", count=10, block_ms=200)
    assert len(msgs) == 1
    assert msgs[0].payload["event_id"] == "e1"

    bus.ack(topic, group, msgs[0].msg_id)
    # ack 후 새 메시지 없음
    assert bus.consume(topic, group, "c1", count=10, block_ms=100) == []


def test_two_consumers_split_messages():
    bus, topic, group = _bus(), _topic(), "g"
    bus.ensure_group(topic, group)
    for i in range(4):
        bus.publish(topic, key="s", payload={"event_id": f"e{i}"})

    a = bus.consume(topic, group, "ca", count=2, block_ms=200)
    b = bus.consume(topic, group, "cb", count=2, block_ms=200)
    ids = {m.payload["event_id"] for m in a + b}
    assert ids == {"e0", "e1", "e2", "e3"}  # 분할·전수 전달, 중복 없음
    assert len(a) + len(b) == 4


def test_unacked_message_is_claimable():
    bus, topic, group = _bus(), _topic(), "g"
    bus.ensure_group(topic, group)
    bus.publish(topic, key="s", payload={"event_id": "e1"})
    bus.consume(topic, group, "ca", count=10, block_ms=200)  # ca가 ack 없이 점유

    claimed = bus.claim_stale(topic, group, "cb", min_idle_ms=0, count=10)
    assert any(m.payload["event_id"] == "e1" for m in claimed)


def test_dead_letter_moves_and_acks():
    bus, topic, group = _bus(), _topic(), "g"
    bus.ensure_group(topic, group)
    bus.publish(topic, key="s", payload={"event_id": "e1"})
    a = bus.consume(topic, group, "ca", count=10, block_ms=200)

    bus.to_dead_letter(topic, group, a[0], reason="boom")

    items = bus.dead_letter_items(topic)
    assert any(m.payload["event_id"] == "e1" for m in items)
    # dead-letter 이동 시 원 PEL에서 ack됨 → 더 이상 claim 안 됨
    claimed = bus.claim_stale(topic, group, "cb", min_idle_ms=0, count=10)
    assert all(m.payload["event_id"] != "e1" for m in claimed)
