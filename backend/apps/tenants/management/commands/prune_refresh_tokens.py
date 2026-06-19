from django.core.management.base import BaseCommand

from apps.tenants.refresh_tokens import prune_refresh_tokens


class Command(BaseCommand):
    help = "만료·폐기된 RefreshToken row를 삭제한다(ADR-0013 GC). 주기 작업으로 호출."

    def handle(self, *args, **options):
        deleted = prune_refresh_tokens()
        self.stdout.write(self.style.SUCCESS(f"pruned {deleted} refresh token(s)"))
