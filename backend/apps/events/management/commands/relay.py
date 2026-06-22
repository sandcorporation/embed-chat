"""relay 프로세스 — outbox를 EventBus로 드레인한다(싱글톤, issue 144/149).

  python manage.py relay          # LISTEN/NOTIFY 루프(부팅 sweep 포함)
  python manage.py relay --once   # 1회 드레인 후 종료(테스트/운영 점검용)
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Drain the event outbox to the EventBus (singleton relay)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="한 번만 드레인하고 종료")

    def handle(self, *args, **opts):
        from apps.events.bus import RedisStreamsBus
        from apps.events.relay import drain_once, run_relay

        if opts["once"]:
            n = drain_once(RedisStreamsBus())
            self.stdout.write(f"drained {n}")
        else:
            run_relay()
