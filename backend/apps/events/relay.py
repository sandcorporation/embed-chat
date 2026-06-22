"""relay — outbox를 EventBus로 드레인하는 단일(싱글톤) 프로세스 (issue 144).

정상 경로는 LISTEN/NOTIFY로 즉시 드레인하고, 부팅/재연결 시 미발행 outbox 행을 한 번
쓸어담는다(catch-up sweep — NOTIFY 유실 안전망). 단일 인스턴스라 outbox id 순서가 보존된다.
발행 성공한 행만 prune하고 event_store(감사)는 건드리지 않는다.
"""
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


def run_relay(bus=None, idle_drain=5.0, stop=None) -> None:
    """Redis pub/sub wake로 깨어 outbox를 드레인한다(부팅 sweep + 주기 backstop 포함).

    record_event가 커밋 후 쏘는 wake를 구독해 저지연으로 드레인하고, wake가 없어도 idle_drain
    마다 한 번 드레인해 유실된 wake를 회수한다(정합성 backstop). 발행 실패는 다음 깨움에 재시도.
    pg LISTEN/NOTIFY 대신 이미 쓰는 Redis pub/sub라 psycopg3 비호환·플랫폼 문제가 없다.
    """
    from apps.events.bus import RedisStreamsBus
    from apps.events.wake import OUTBOX_WAKE_CHANNEL, _redis

    bus = bus or RedisStreamsBus()
    pubsub = _redis().pubsub()
    pubsub.subscribe(OUTBOX_WAKE_CHANNEL)
    try:
        drain_once(bus)  # 부팅 catch-up sweep
        while stop is None or not stop():
            pubsub.get_message(timeout=idle_drain)  # wake 시 즉시 반환, 없으면 idle_drain마다(backstop)
            try:
                drain_once(bus)
            except Exception:
                pass
    finally:
        pubsub.unsubscribe(OUTBOX_WAKE_CHANNEL)
        pubsub.close()
