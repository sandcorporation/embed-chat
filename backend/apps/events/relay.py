"""relay — outbox를 EventBus로 드레인하는 단일(싱글톤) 프로세스 (issue 144).

정상 경로는 LISTEN/NOTIFY로 즉시 드레인하고, 부팅/재연결 시 미발행 outbox 행을 한 번
쓸어담는다(catch-up sweep — NOTIFY 유실 안전망). 단일 인스턴스라 outbox id 순서가 보존된다.
발행 성공한 행만 prune하고 event_store(감사)는 건드리지 않는다.
"""
import time


def drain_once(bus, batch=200) -> int:
    """미발행 outbox 행을 id 순서로 발행하고 prune한다. 발행 실패 시 그 행부터 남긴다(재발행)."""
    from apps.events.models import Outbox

    rows = list(Outbox.objects.filter(published_at__isnull=True).order_by("id")[:batch])
    published = 0
    for row in rows:
        bus.publish(row.topic, row.key, row.envelope)  # 실패하면 예외 전파 → 이 행은 prune 안 됨
        row.delete()
        published += 1
    return published


def run_relay(bus=None, poll_interval=1.0, stop=None) -> None:
    """주기적 드레인 루프(부팅 sweep 포함). 매 틱 미발행 outbox를 드레인하므로 그 자체가
    연속 catch-up sweep이다. 발행 실패는 다음 틱에 재시도(루프는 죽지 않음).

    NOTE: record_event는 pg_notify를 쏘지만(저지연 wake 용도), psycopg3에서 Django 연결로
    LISTEN/select를 안전하게 엮기가 까다로워 v1은 짧은 주기 폴링으로 정확성을 보장한다. NOTIFY
    기반 sub-second wake는 후속 최적화(전용 psycopg3 연결).
    """
    from apps.events.bus import RedisStreamsBus

    bus = bus or RedisStreamsBus()
    while stop is None or not stop():
        try:
            drain_once(bus)
        except Exception:
            pass
        time.sleep(poll_interval)
