# missour.ai

Has separate environments for ML Experiments and Django Application.  Changes in ML experiments do not affect the production web app environment.

- The ML environment is pinned to Python 3.11.6 via Pyenv and Poetry.
- The Django application is containerized and uses Python 3.11.x via Docker images.

*Django Application*
To run the Django application, run `docker-compose up` within the main directory.

*ML Environment*
To use the ML Experiments environment, do the following
1. Go into the `ml_env` directory.
2. Run `poetry shell` to activate the environment
3. Within the activated environment run `poetry run jupyter notebook` to execute the Jupyter server.
4. Install additional packages within the poetry shell (e.g. `langchain`)

## Prerequisites

Make sure you have the following tools installed:

- Docker: Install Docker
- Docker Compose: Install Docker Compose

Get OpenAI API Key and store in `.env` file as `OPENAI_API_KEY` (ensure that this is in your `.gitignore`!)

## Usage

Start Django application by running `docker-compose up`.  Application will be visible at [http://localhost:8000](http://localhost:8000)

The logic for transcribing the files is contained within `src`, but currently integrating this into the django application.  Process for executing this is included for reference below:

1. Place files that you want to transcribe in the `audio-files` folder (currently only validated against MP3 file types).
2. Exec into the running docker container and run `main.py`.  This will output transcripts in the `/transcripts` folder.e
3. Recommend maintaining audio files and transcripts in these folders with initial naming conventions as the script currently validates that audio files are not transcribed multiple times and saving credits.  Plan to implement a better method for validating that files aren't transcribed multiple times.