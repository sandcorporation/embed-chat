from django.db import migrations, models


def backfill_existing_agents_admin(apps, schema_editor):
    """기존 TenantAgent 전원을 Admin으로 백필 — 역할 도입 전엔 모두 전권이었으므로 접근/권한 보존(ADR-0025)."""
    TenantAgent = apps.get_model("tenants", "TenantAgent")
    TenantAgent.objects.update(role="admin")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0003_scope_refusal_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantagent",
            name="role",
            field=models.CharField(
                choices=[("admin", "Admin"), ("member", "Member")],
                default="member",
                max_length=10,
            ),
        ),
        migrations.RunPython(backfill_existing_agents_admin, noop_reverse),
    ]
