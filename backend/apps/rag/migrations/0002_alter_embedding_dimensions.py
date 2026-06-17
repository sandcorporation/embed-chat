import pgvector.django
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rag", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentchunk",
            name="embedding",
            field=pgvector.django.VectorField(dimensions=1024),
        ),
    ]
