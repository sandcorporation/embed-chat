"""dead-letter 조회·수동 리플레이 (issue 152).

  python manage.py events_dlq list                 # dead-letter 항목 조회
  python manage.py events_dlq replay               # 전부 원 스트림으로 되돌려 재처리
  python manage.py events_dlq list --topic=signals.presence

자동 재처리 루프는 두지 않는다(poison 폭풍 방지) — 운영자가 원인을 고친 뒤 직접 실행한다.
재처리는 멱등(processed_events)이라 이미 성공한 소비자는 다시 효과를 내지 않는다.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "List or replay dead-lettered events."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["list", "replay"])
        parser.add_argument("--topic", default=None)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **opts):
        from apps.events.bus import RedisStreamsBus
        from apps.events.store import default_topic

        bus = RedisStreamsBus()
        topic = opts["topic"] or default_topic()
        items = bus.dead_letter_items(topic, count=opts["limit"])

        if opts["action"] == "list":
            for m in items:
                p = m.payload
                self.stdout.write(
                    f"{p.get('event_id')} {p.get('type')} agg={p.get('aggregate_id')} "
                    f"reason={p.get('_dlq_reason')}"
                )
            self.stdout.write(f"total {len(items)}")
            return

        # replay: 원 봉투(_dlq_reason 제거)를 메인 스트림으로 재발행 → 소비자 재처리, DLQ에서 제거.
        replayed_ids = []
        for m in items:
            envelope = {k: v for k, v in m.payload.items() if k != "_dlq_reason"}
            bus.publish(topic, key=envelope.get("aggregate_id", ""), payload=envelope)
            replayed_ids.append(m.msg_id)
        bus.remove_dead_letter(topic, replayed_ids)
        self.stdout.write(f"replayed {len(replayed_ids)}")
