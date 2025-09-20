# missour.ai

Has separate environments for ML Experiments and Web Application. Changes in ML experiments do not affect the production web app environment.

- The ML environment is pinned to Python 3.11.6 via Pyenv and Poetry.
- The web application runs on Python 3.11.x inside Docker images.

## Prerequisites

Make sure you have the following tools installed:

- Docker
- Node.js (for running the Vite dev server)
- Poetry: For managing the ML Environment

Get OpenAI API Key and store in `.env` file as `OPENAI_API_KEY` (ensure that this is in your `.gitignore`!)

## Web Application
The web application combines a Django backend that exposes APIs and serves the HTML shell with a React frontend built with Vite. Django runs inside a container, while Vite handles hot-reload and asset delivery during development.

**Development**
1. Build the backend image (first time or after Dockerfile changes): `docker build -f backend-dev.Dockerfile -t missourai-backend:dev .`
2. Start the backend container from the repository root:
   `docker run --rm -it -p 8000:8000 -e DJANGO_VITE_DEV=1 -v "${PWD}:/app" -w /app/missourai_django missourai-backend:dev`
   - In Windows PowerShell, `${PWD.Path}` expands to the current directory; adjust the flag to `-v "${PWD.Path}:/app"` if needed for your shell.
   - The bind mount keeps Django in sync with local template and code changes.
3. In another terminal, run the React/Vite dev server:
   ```
   cd frontend
   npm install
   npm run dev
   ```
4. Open `http://localhost:8000/transcription/dashboard/` to see the integrated React dashboard backed by Django APIs.

**Production**
- TBD � production build and deployment process for the web application is still being defined.

## ML Environment
To use the ML Experiments environment, do the following
1. Go into the `ml_env` directory.
2. Run `poetry shell` to activate the environment
3. Within the activated environment run `poetry run jupyter notebook` to execute the Jupyter server.
4. Install additional packages within the poetry shell (e.g. `langchain`)
