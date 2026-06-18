from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rag", "0004_delete_documentchunk"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="source_type",
            field=models.CharField(max_length=10, default="file"),
        ),
        migrations.AddField(
            model_name="document",
            name="source_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]
