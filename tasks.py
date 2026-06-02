import os
from urllib.parse import quote

from celery import Celery

rabbitmq_user = quote(os.getenv("RABBITMQ_DEFAULT_USER", "guest"), safe="")
rabbitmq_password = quote(os.getenv("RABBITMQ_DEFAULT_PASS", "guest"), safe="")
broker_url = os.getenv(
    "CELERY_BROKER_URL",
    f"amqp://{rabbitmq_user}:{rabbitmq_password}@rabbitmq:5672//",
)

app = Celery("tasks", broker=broker_url)

@app.task
def add(x, y):
    return x + y
