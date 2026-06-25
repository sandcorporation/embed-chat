from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_topic_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantconfig",
            name="scope_refusal_message",
            field=models.TextField(blank=True, default=""),
        ),
    ]
