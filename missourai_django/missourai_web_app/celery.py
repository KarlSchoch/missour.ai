import os

from celery import Celery

# Import Celery settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'missourai_web_app.settings')

app = Celery('missourai_web_app')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")