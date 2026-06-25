from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0004_tenantagent_role"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="tenant",
            constraint=models.UniqueConstraint(Lower("name"), name="uq_tenant_name_ci"),
        ),
    ]
