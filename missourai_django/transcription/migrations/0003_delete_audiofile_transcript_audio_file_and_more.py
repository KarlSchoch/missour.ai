# Generated by Django 5.1.2 on 2024-12-08 20:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transcription', '0002_transcript'),
    ]

    operations = [
        migrations.DeleteModel(
            name='AudioFile',
        ),
        migrations.AddField(
            model_name='transcript',
            name='audio_file',
            field=models.FileField(default='uploads/audio/placeholder.mp3', upload_to='uploads/audio/'),
        ),
        migrations.AlterField(
            model_name='transcript',
            name='name',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='transcript',
            name='transcript_file',
            field=models.TextField(),
        ),
    ]
