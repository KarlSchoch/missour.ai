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
   `docker run --rm --env-file .env -it -p 8000:8000 -e DJANGO_VITE_DEV=1 -v "${PWD}:/app" -w /app/missourai_django missourai-backend:dev`
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
- TBD - production build and deployment process for the web application is still being defined.

### Key Configurations

- **Django owns the HTML shell.** Every UI page extends `missourai_django/transcription/templates/transcription/base.html` so that the global navigation, fonts, and `static/transcription/css/style.css` styling are always present.
- **Vite assets are mounted under `/static/`.** The `base: '/static/'` setting in `frontend/vite.config.js` matches Django's `STATIC_URL`, so `{% vite_asset 'src/...' %}` resolves correctly in templates without extra URL rewriting.
- **Dev traffic proxies through Django.** The Vite dev server proxies `'/api'` to `http://localhost:8000/` to reuse Django's session and CSRF cookies while developing React apps (`frontend/vite.config.js` -> `server.proxy`).
- **Initial payloads come from Django views.** Each page view returns an `initial_payload` dictionary that gets serialized with `{{ initial_payload|json_script:"initial-payload" }}` and can be read by React via `document.getElementById('initial-payload')`.
- **CSRF stays consistent across fetches.** Frontend code imports `getCsrfToken` from `frontend/src/utils/csrf.js`, ensuring POST/PUT/PATCH requests include the same `csrftoken` cookie Django issued.

### Creating New Pages

**Overview**
1. Create or update a Django view that prepares any data the page needs and renders a template extending the shared base.
2. Register a URL in `missourai_django/transcription/ui_urls.py` that points to the view so Django can serve the page.
3. Add a new React entry file in `frontend/src` and load it from the template with `{% vite_asset %}`.
4. Expose any required backend APIs under `missourai_django/transcription/api_urls.py` so the React page can fetch data.

#### Step 1 - Scaffold the Django view and template
1. Add (or update) a view in `missourai_django/transcription/views.py` that returns the data React will bootstrap from:
   ```python
   def reports(request):
       payload = {"apiUrls": {"list": "/api/reports/"}}
       return render(request, "transcription/reports.html", {"initial_payload": payload})
   ```
2. Create `missourai_django/transcription/templates/transcription/reports.html` that extends the base layout, mounts a React root, and registers the Vite bundle:
   ```django
   {% extends "transcription/base.html" %}
   {% load django_vite %}

{% block title %}Reports - missour.ai{% endblock %}

   {% block content %}
   <div id="reports-root"></div>
   {{ initial_payload|json_script:"initial-payload" }}
   {% endblock %}

   {% block extra_scripts %}
       {% vite_hmr_client %}
       {% vite_asset 'src/reports.jsx' %}
   {% endblock %}
   ```
3. **Checkpoint:** Run the backend (`docker run ...` command in the Development section) and visit the new route - the navigation and base styling should render, even though the React area is empty.

#### Step 2 - Register the UI route
1. Add a path to `missourai_django/transcription/ui_urls.py`, e.g. `path('reports/', views.reports, name='reports')`.
2. Include a link from existing navigation if desired.
3. **Checkpoint:** `python manage.py runserver` and open `http://localhost:8000/transcription/reports/` - you should see the blank template with the global layout.

#### Step 3 - Build the React entry file
1. Create `frontend/src/reports.jsx` that reads the initial payload, mounts on the matching DOM node, and imports shared helpers:
   ```jsx
   import React from 'react'
   import ReactDOM from 'react-dom/client'
   import { getCsrfToken } from './utils/csrf'

   function getInitialData() {
     const el = document.getElementById('initial-payload')
     return el ? JSON.parse(el.textContent) : {}
   }

   function ReportsApp() {
     const init = React.useMemo(getInitialData, [])
     // component code goes here
     return <div>{init.username}</div>
   }

   const mount = document.getElementById('reports-root')
   if (mount) ReactDOM.createRoot(mount).render(<ReportsApp />)
   ```
2. Start the Vite dev server (`npm run dev` inside `frontend`) to compile and hot-reload the new entry point.
3. **Checkpoint:** With both Django and Vite running, reload the page and confirm the React component hydrates (inspect DevTools console for any missing mount errors).

#### Step 4 - Provide backend APIs (if needed)
1. Define or update API views/serializers for the new React page in `missourai_django/transcription/api_urls.py` and associated view modules.
2. Ensure the endpoints rely on Django's session authentication so the proxied Vite requests keep working in dev.
3. **Checkpoint:** Call the API directly (e.g. from the browser console: `fetch(init.apiUrls.list).then(r => r.json())`) to verify it returns expected data before wiring it into the React UI.

With these steps, every new page automatically inherits the Django styling, navigation, and CSRF/session handling while keeping the React code focused on page-specific logic.

## ML Environment
To use the ML Experiments environment, do the following
1. Go into the `ml_env` directory.
2. Run `poetry shell` to activate the environment
3. Within the activated environment run `poetry run jupyter notebook` to execute the Jupyter server.
4. Install additional packages within the poetry shell (e.g. `langchain`)
