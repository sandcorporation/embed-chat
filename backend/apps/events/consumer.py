"""소비자 런타임 — 멱등 + 제한 재시도 + DLQ (issue 145).

모든 이벤트 소비자가 공유하는 단일 루프. consumer-group으로 읽어 등록 핸들러에 디스패치하고,
processed_events로 중복(at-least-once 재전달)을 막고, 핸들러가 제한 횟수 실패하면 dead-letter로
보낸다. 코드는 하나이며 group 이름만 파라미터로 다르다(--group=<name>은 management command).
"""
import logging

logger = logging.getLogger(__name__)

# group 이름 → handler(envelope) 레지스트리. 각 소비자 슬라이스(146~150)가 등록한다.
_HANDLERS = {}


def register_handler(group: str, handler) -> None:
    _HANDLERS[group] = handler


def get_handler(group: str):
    return _HANDLERS[group]


class EventConsumer:
    """한 consumer-group의 소비 루프. handler(envelope)를 멱등·제한재시도·DLQ로 구동한다."""

    def __init__(self, bus, topic, group, consumer, handler, max_attempts=5):
        self.bus = bus
        self.topic = topic
        self.group = group
        self.consumer = consumer
        self.handler = handler
        self.max_attempts = max_attempts
        bus.ensure_group(topic, group)

    def process_once(self, count=20, block_ms=1000, min_idle_ms=0) -> int:
        """크래시로 남은 pending 회수 + 신규 메시지를 처리한다. 처리한 건수를 반환."""
        handled = 0
        for msg in self.bus.claim_stale(self.topic, self.group, self.consumer, min_idle_ms, count):
            self._handle(msg); handled += 1
        for msg in self.bus.consume(self.topic, self.group, self.consumer, count, block_ms):
            self._handle(msg); handled += 1
        return handled

    def _handle(self, msg) -> None:
        from apps.events.models import ProcessedEvent

        event_id = msg.payload.get("event_id")
        # 멱등: 이미 처리한 이벤트면 핸들러 호출 없이 ack만.
        if event_id and ProcessedEvent.objects.filter(consumer_group=self.group, event_id=event_id).exists():
            self.bus.ack(self.topic, self.group, msg.msg_id)
            return

        last_exc = None
        for _ in range(self.max_attempts):
            try:
                self.handler(msg.payload)
                if event_id:
                    ProcessedEvent.objects.get_or_create(consumer_group=self.group, event_id=event_id)
                self.bus.ack(self.topic, self.group, msg.msg_id)
                return
            except Exception as exc:  # noqa: BLE001 — 핸들러 실패는 재시도/DLQ 대상
                last_exc = exc

        # 제한 횟수 소진 → dead-letter로 이동(+원 PEL ack). 소비자는 멈추지 않는다.
        logger.warning("event %s dead-lettered after %d attempts: %s", event_id, self.max_attempts, last_exc)
        self.bus.to_dead_letter(self.topic, self.group, msg, reason=str(last_exc))


def run_consumer(group: str, bus=None, topic=None, consumer=None, stop=None) -> None:
    """management command 진입점 — 등록된 핸들러로 group 소비 루프를 돈다(149)."""
    from apps.events.bus import RedisStreamsBus
    from apps.events.store import default_topic

    bus = bus or RedisStreamsBus()
    ec = EventConsumer(bus, topic or default_topic(), group, consumer or f"{group}-1", get_handler(group))
    while stop is None or not stop():
        ec.process_once()
