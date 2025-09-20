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
