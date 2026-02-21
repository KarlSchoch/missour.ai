# Stage 1: build frontend assets with Vite
FROM node:20-slim AS node-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

# Stage 2: install Python deps with Poetry
FROM python:3.12-slim AS python-build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ffmpeg libavcodec-extra && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root
COPY . .
COPY --from=node-build /frontend/dist ./frontend/dist
RUN ./.venv/bin/python missourai_django/manage.py collectstatic --noinput

# Stage 3: runtime image
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_VITE_DEV=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libavcodec-extra && rm -rf /var/lib/apt/lists/*
WORKDIR /app/missourai_django
COPY --from=python-build /app /app
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/app/.venv/bin/uvicorn", "missourai_web_app.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# Stage 4: dev image with Poetry available for on-start installs
FROM python-build AS dev
ENV DJANGO_VITE_DEV=true
WORKDIR /app
COPY docker/entrypoint.dev.sh /entrypoint.dev.sh
RUN sed -i 's/\r$//' /entrypoint.dev.sh && chmod +x /entrypoint.dev.sh
ENTRYPOINT ["/entrypoint.dev.sh"]
CMD ["/app/.venv/bin/python", "manage.py", "runserver", "0.0.0.0:8000"]
