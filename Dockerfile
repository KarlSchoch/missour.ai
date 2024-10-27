# Use an official Python image as the base image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install curl, ntpdate, ffmpeg, and libavcodec-extra for extra codec support
RUN apt-get update && \
    apt-get install -y apt-transport-https curl ffmpeg libavcodec-extra && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Ensure Poetry is available in the PATH
ENV PATH="/root/.local/bin:$PATH"

# Configure Poetry to not use a virtual environment
RUN poetry config virtualenvs.create false

# Copy only the poetry files to leverage Docker cache if dependencies don't change
COPY pyproject.toml poetry.lock* /app/

# Install dependencies defined in the Poetry files
RUN poetry install --no-interaction --no-ansi

# Copy the rest of the project
COPY . /app

# Set the working directory to the django app
# Maintaining the /src/ side for logic on executing transcription, but will be integrated into the django app
WORKDIR /app/missourai_django

# Migrate the database
CMD ["poetry", "run", "python", "manage.py", "migrate"]

# Run the web app
CMD ["poetry", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]