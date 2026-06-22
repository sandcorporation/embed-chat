"""DLQ 리플레이 CLI (issue 152). 실 Redis Streams."""
import uuid
import pytest
from django.core.management import call_command


def _bus():
    from apps.events.bus import RedisStreamsBus
    return RedisStreamsBus()


def _dead_letter_one(bus, topic, group):
    """failing 핸들러로 이벤트 1건을 DLQ로 보낸다. event_id 반환."""
    from apps.events.consumer import EventConsumer
    ev_id = str(uuid.uuid4())
    bus.ensure_group(topic, group)
    bus.publish(topic, key="s", payload={"event_id": ev_id, "type": "X", "aggregate_id": "s"})

    def boom(env):
        raise RuntimeError("boom")

    EventConsumer(bus, topic, group, "c", boom, max_attempts=1).process_once(block_ms=200)
    return ev_id


@pytest.mark.django_db
def test_dlq_list_counts_items(capsys):
    bus, topic, group = _bus(), f"test.dlq.{uuid.uuid4().hex}", "g"
    _dead_letter_one(bus, topic, group)

    call_command("events_dlq", "list", f"--topic={topic}")

    out = capsys.readouterr().out
    assert "total 1" in out


@pytest.mark.django_db
def test_dlq_replay_clears_and_reprocesses():
    from apps.events.consumer import EventConsumer
    bus, topic, group = _bus(), f"test.dlq.{uuid.uuid4().hex}", "g"
    ev_id = _dead_letter_one(bus, topic, group)
    assert len(bus.dead_letter_items(topic)) == 1

    call_command("events_dlq", "replay", f"--topic={topic}")

    assert len(bus.dead_letter_items(topic)) == 0  # DLQ 비워짐(중복 리플레이 방지)
    # 메인 스트림으로 되돌아가 정상 핸들러가 재처리한다
    seen = []
    EventConsumer(bus, topic, group, "c2", lambda env: seen.append(env["event_id"])).process_once(block_ms=200)
    assert ev_id in seen
