from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("transcription", "0020_seed_initial_usage_pricing")]

    operations = [
        migrations.AddField(
            model_name="chunk", name="is_superseded",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="chunk", name="position",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
