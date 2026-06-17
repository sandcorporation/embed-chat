from django.core.management.base import BaseCommand
from apps.tenants.models import Operator


class Command(BaseCommand):
    help = "E2E 테스트용 Operator 계정을 생성한다 (이미 존재하면 skip)."

    def add_arguments(self, parser):
        parser.add_argument('--username', default='admin')
        parser.add_argument('--password', default='admin123')
        parser.add_argument('--email', default='admin@test.com')

    def handle(self, *args, **options):
        username = options['username']
        if Operator.objects.filter(username=username).exists():
            self.stdout.write(f'Operator "{username}" already exists — skipping.')
            return
        Operator.objects.create_superuser(
            username=username,
            email=options['email'],
            password=options['password'],
        )
        self.stdout.write(self.style.SUCCESS(f'Created operator "{username}".'))
