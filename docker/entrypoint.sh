#!/bin/sh
set -e
# Run migrations from the project root (workdir is /app/missourai_django)
/app/.venv/bin/python manage.py migrate --noinput
/app/.venv/bin/python manage.py validate_usage_pricing
exec "$@"
