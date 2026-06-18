from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0006_tenant_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="require_identity_verification",
            field=models.BooleanField(default=False),
        ),
    ]
