import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "django-ninja OpenAPI 스키마를 JSON으로 export한다(orval 입력·드리프트 기준). 서버 불필요."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", "-o", default="openapi.json",
            help="출력 파일 경로(기본: openapi.json)",
        )

    def handle(self, *args, **options):
        from config.api import api

        schema = dict(api.get_openapi_schema())
        # sort_keys로 결정적 바이트 출력 → 드리프트 체크가 안정적
        text = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True)
        with open(options["output"], "w", encoding="utf-8") as f:
            f.write(text)
        self.stdout.write(self.style.SUCCESS(f"exported OpenAPI to {options['output']}"))
