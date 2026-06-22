"""이벤트 소비자 프로세스 — group별 핸들러 루프(issue 145/149).

코드는 하나이며 --group으로 webhook/visitor-bridge/console-bridge/presence-bridge를 고른다.

  python manage.py consume_events --group=webhook
  python manage.py consume_events --group=webhook --once   # 1회 처리 후 종료(테스트)
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run an event consumer for the given group."

    def add_arguments(self, parser):
        parser.add_argument("--group", required=True)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--topic", default=None)
        parser.add_argument("--consumer", default=None)

    def handle(self, *args, **opts):
        import apps.events.handlers  # noqa: F401 — group→handler 등록
        from apps.events.bus import RedisStreamsBus
        from apps.events.consumer import EventConsumer, get_handler, run_consumer
        from apps.events.store import default_topic

        group = opts["group"]
        topic = opts["topic"] or default_topic()
        consumer = opts["consumer"] or f"{group}-1"

        if opts["once"]:
            bus = RedisStreamsBus()
            EventConsumer(bus, topic, group, consumer, get_handler(group)).process_once(block_ms=500)
        else:
            run_consumer(group, topic=topic, consumer=consumer)
