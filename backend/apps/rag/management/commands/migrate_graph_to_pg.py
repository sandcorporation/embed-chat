"""GraphStore 데이터 이전 — Neo4j → Postgres+pgvector (issue 166).

  python manage.py migrate_graph_to_pg                 # 전체 테넌트
  python manage.py migrate_graph_to_pg --tenant=<id>   # 단일 테넌트

임베딩을 재계산하지 않고 그대로 옮긴다(멱등 — 재실행 안전). 컷오버(167) 전/시점에 실행한다.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "기존 테넌트 그래프를 Neo4j에서 Postgres+pgvector로 이전한다(임베딩 보존)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default=None, help="단일 테넌트 id(미지정 시 전체)")

    def handle(self, *args, **opts):
        from apps.tenants.models import Tenant
        from apps.rag.graph_migrate import migrate_tenant

        if opts["tenant"]:
            tenant_ids = [opts["tenant"]]
        else:
            tenant_ids = [str(t.id) for t in Tenant.objects.all()]

        for tid in tenant_ids:
            counts = migrate_tenant(tid)
            self.stdout.write(f"tenant {tid}: {counts}")
        self.stdout.write(self.style.SUCCESS(f"이전 완료 — {len(tenant_ids)} 테넌트"))
