#!/bin/sh
set -e

cd /app
poetry install --no-root --only main

/app/.venv/bin/python /app/missourai_django/manage.py migrate --noinput
cd /app/missourai_django
exec "$@"
