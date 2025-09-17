#Use an official Python image as the base image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set the working directory inside the container
WORKDIR /app

# Install curl, ntpdate, ffmpeg, and libavcodec-extra for extra codec support
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ffmpeg libavcodec-extra && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Poetry Config
ENV PATH="/root/.local/bin:${PATH}"
RUN ln -s /root/.local/bin/poetry /usr/local/bin/poetry || true
ENV POETRY_VIRTUALENVS_CREATE=false
COPY pyproject.toml poetry.lock* /app/

# Install dependencies defined in the Poetry files
RUN poetry install --no-interaction --no-ansi

# Copy the rest of the project
COPY . /app

# Set the working directory to the django app
# Maintaining the /src/ side for logic on executing transcription, but will be integrated into the django app
WORKDIR /app/missourai_django

# Run the web app
CMD ["bash", "-lc", "poetry run python manage.py migrate && poetry run python manage.py runserver 0.0.0.0:8000"]
