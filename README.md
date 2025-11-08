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
- **Initial payloads come from Django views.** Each page view returns an `initial_payload` dictionary that gets serialized with `{{ initial_payload|json_script:"initial-payload" }}` and can be read by React via `document.getElementById('initial-payload')`.  This `initial_payload ` is generated from the view
- **CSRF stays consistent across fetches.** Frontend code imports `getCsrfToken` from `frontend/src/utils/csrf.js`, ensuring POST/PUT/PATCH requests include the same `csrftoken` cookie Django issued.

### Creating New Pages

**Overview**
For reference, the *Dashboard* page provides an example for the process described below.
1. Create or update a Django view that prepares any data the page needs and renders a template extending the shared base.
2. Register a URL in `missourai_django/transcription/ui_urls.py` that points to the view so Django can serve the page.
3. Add a new React entry file in `frontend/src` and load it from the template with `{% vite_asset %}`.
4. Expose any required backend APIs under `missourai_django/transcription/api_urls.py` so the React page can fetch data.

#### Step 1 - Scaffold the Django view and template
1. Add (or update) a view in `missourai_django/transcription/views.py` that returns the data React will bootstrap from.  Adding the `apiUrls` and `initial_payload` keys to the payload and responses, respectively, ensure that your React application has access to necessary elements uponinitial startup (you can include other parameters as necessary).
   ```python
   def reports(request):
       payload = {"apiUrls": {"list": "/api/<some-name>/"}}
       return render(request, "transcription/<some-name>.html", {"initial_payload": payload})
   ```
2. Create `missourai_django/transcription/templates/transcription/<some-name>.html` that extends the base layout, mounts a React root, and registers the Vite bundle.  
   - `{% block extra_scripts %}`: Executes code necessary for allowing Django to access React/Vite elements

   ```django
   {% extends "transcription/base.html" %}
   {% load django_vite %} # Boilerplate for integrating Django and Vite
   {% load vite_extras %} # Loads templatetags/vite_extras.py that contains vite_react_refresh

   {% block title %}Reports - missour.ai{% endblock %}

   {% block content %}
   # Create HTLM element node for your page
   <div id="<some-name>-root"></div>
   # Pull `initial_payload` defined in view into the page's HTML as a script with id `initial-payload`
   {{ initial_payload|json_script:"initial-payload" }}
   {% endblock %}

   {% block extra_scripts %}
      # Enables Vite, React, and Django to function in Dev mode
      {% vite_react_refresh %}
      {% vite_hmr_client %} # Boilerplate for integrating Django and Vite
      {% vite_asset 'src/reports.jsx' %} # Pulls in React Component
   {% endblock %}
   ```
3. **Checkpoint:** Run the backend (`docker run ...` command in the Development section) and visit the new route - the navigation and base styling should render, even though the React area is empty.

#### Step 2 - Register the UI route
1. Add a path to `missourai_django/transcription/ui_urls.py`, e.g. `path('<some-name>/', views.<some-name>, name='<some-name>')`.
2. Include a link from existing navigation if desired.
3. **Checkpoint:** `python manage.py runserver` and open `http://localhost:8000/transcription/<some-name>/` - you should see the blank template with the global layout.

#### Step 3 - Build the React entry file
1. Create `frontend/src/<some-name>.jsx` that reads the initial payload, mounts on the matching DOM node, and imports shared helpers:
   ```jsx
   import React from 'react'
   import ReactDOM from 'react-dom/client'
   // Imports utility function for pulling Django CSRF token
   import { getCsrfToken } from './utils/csrf'

   // Pulls initial-data HTML element created in Django template
   function getInitialData() {
     const el = document.getElementById('initial-payload')
     return el ? JSON.parse(el.textContent) : {}
   }

   function ReportsApp() {
     const init = React.useMemo(getInitialData, [])
     // component code goes here
     return <div>Your Wonderful Content</div>
   }

   // Mount your React component at the HTLM element node created in Django template
   const mount = document.getElementById('<some-name>-root')
   if (mount) ReactDOM.createRoot(mount).render(<App />)
   ```
2. Start the Vite dev server (`npm run dev` inside `frontend`) to compile and hot-reload the new entry point.
3. **Checkpoint:** With both Django and Vite running, reload the page and confirm the React component hydrates (inspect DevTools console for any missing mount errors).

#### Step 4 - Provide backend APIs (if needed)
1. Define or update API views/serializers for the new React page in `missourai_django/transcription/api_urls.py` and associated view modules.
2. Ensure the endpoints rely on Django's session authentication so the proxied Vite requests keep working in dev.  See the code below for an illustration of how to leverage Django's CSRF Token.

   ```jsx
   await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ name: `Item ${Date.now()}` }),
    })
   ```

3. **Checkpoint:** Call the API directly (e.g. from the browser console: `fetch(init.apiUrls.list).then(r => r.json())`) to verify it returns expected data before wiring it into the React UI.

With these steps, every new page automatically inherits the Django styling, navigation, and CSRF/session handling while keeping the React code focused on page-specific logic.

### Adding React Components to existing Django Pages
Given that Missour.ai was initially built in pure Django, there are a number of "backbone" pages that are written in Django and it is useful to be able to add React components to these pages rather than recreate that existing page in React.  This section outlines the process for doing it

**Overview**
1. Create React Component
2. Add Boilerplate to Existing Django Page's Template
3. Create Django template for your **partial**
4. Create Django view for React template

#### Step 1: Create React Component
This is exactly the same as the process covered in [Step 3 - Build the React entry file](#step-3---build-the-react-entry-file).

#### Step 2: Add Boilerplate to Existing Django Page's Template
Since the Django template for the existing page is now "managing" the React component, you need to add much of the same boilerplate that you included in [Step 1 - Scaffold the Django View and Template](#step-1---scaffold-the-django-view-and-template) to the exisiting Django template as shown in the code below.

The main thing to notice that is *new* for this implementation compared to managing the entire page in React is that you need to create a new `{% block %}` for the React component at the location where you want it to be pulled in within the template that references the template for your partial using an `{% include %}` statement
```html
<!-- Existing loads, extends, etc. -->
{% load django_vite vite_extras %}
{% block content %}
   <!-- Existing elements -->
    {% block <relevant-section-name> %}
        {% include 'transcription/partials/<your-partial-template>.html' %}
    {% endblock %}
{% endblock %}

{% block extra_scripts %}
    {% vite_react_refresh %}
    {% vite_hmr_client %}
    {% vite_asset 'src/<your-react-component>.jsx' %}
{% endblock %}
```

#### Step 3: Create Django template for your **partial**
Given that all of the "management" tasks are handled within the parent file, the contents of this file are very simple.  You just need to create the `<div>` that you referenced within the original react component from earlier in [Step 1](#step-1-create-react-component) and provide the initial payload.  Best practice is to create this within the `templates/transcription/partials` directory for clarity but the main consideration is that it matches what is referenced in the `{% include %}` statement from [Step 2](#step-2-add-boilerplate-to-existing-django-pages-template).

```html
<div id="<id-generated-in-react-component>-root"></div>
{{ initial_payload|json_script:"initial-payload"}}
```

#### Step 4: Create Django view for React template
You can follow the instructions for creating the view from [Step 1](#step-1---scaffold-the-django-view-and-template) of the process for creating an entirely React-based page.

#### Notes
##### Partials
Sometimes, you may need to integrate a react component within an existing Django page, and this section covers some of the key considerations for doing that 

**General Pattern**
1. Partial Template: Place the template for your partial witin `templates/transcription/partials`.  This template should be VERY mininimal and only include a div that your react component will populate and a reference to the `initial_payload`.  This is important because the react component will reach out to the initial component to get values and provides the React component with a connection to the underlying database.
   ```html
   <div id="analyze-audio-page-section-root"></div>
   {{ initial_payload|json_script:"initial-payload"}}
   ```
2. Register Tag: The `{% include 'transcription/partials/<your-partial>.html' %}` pattern that we are using to pull the partial into the parent page (covered later in the section) does not allow for context/data to be pulled into the partial due to the capabilities of `include`.  To deal with this, we registed `inclusion_tag`s that can pass in context.  Examples of this are contained within `missourai_django/transcription/templatetags/transcription_tags.py`, and the general concept is that this is one of the layers of connective tissue between your database and the react component. Ensure that the return value of that function follows the pattern below, as that will allow it to connect to the `{{ initial_payload|json_script:"initial-payload"}}` that you set in the previous step.
   ```python
   # Your logic to create a payload
   return {'initial_payload': payload}
   ```
3. Updating Parent Template: Within the parent template, you will need to first create a `{% block %}` that your partial can integrate into, then call the template tag you registered in the previous step, and finally use `{% include %}` to point to your partial
   ```html
   <form method="POST" enctype="multipart/form-data">
         {% csrf_token %}
         {{ form.as_p }}
         {% block analyze_audio_page_section %}
               {% <template-tag-function> %}
               {% include 'transcription/partials/your-partial-template.html' %}
         {% endblock %}
         <button type="submit">Upload</button>
   </form>
   ```
4. Access Django Data from your React Component: To utilize the data that has been passed from your database through Django to the page within the `initial-payload` element as a JSON, use the pattern below where you define a function that selects the `inital-payload` element and parses the JSON present there and then call that function within the context of `useMemo` to ensure that it only populates once per mount.
   ```javascript
   function getInitialData() {
      const el = document.getElementById("initial-payload");
      return el ? JSON.parse(el.textContent) : {};
   }

   function YourComponent() {
      const init = useMemo(getInitialData, []);
   }

   ```

> *(Special Consideration)* **Passing Data from your Partial to a Form**
> Occasionally, you will need to utilize data captured in your partial to Django via a form to enable some backend computation.  Doing this requires completing two steps: passing the data to your form and then accessing the form data within the view.  
> To pass the data to your form (and thus to the backend), you need to place the `{% block %}` containing your partial within the parent template's <form> tags (i.e. `<form> {% block %} your content {% block %} </form>`).  This partial needs to contain an HTML element with the requisite form data since Django cannot access React's state.  You can achieve this by creating a hidden input tag using the code template below that contains the data from your React partial that you want to pass to the View for processing.
>  ```javascript
>  import React, { useRef, useEffect } from "react";
>  export default function YourComponent() {
>     // variable to hold data to pass to the <input> field
>     const hiddenRef = useRef(null);
>     // Ensure hiddenRef is populated by relevant data from Component
>     useEffect(() => {
>         if (hiddenRef.current) {
>             if (hidden) {
>                 hiddenRef.current.value = JSON.stringify([]);
>             } else {
>                 hiddenRef.current.value = JSON.stringify(Array.from(someVariable));
>             }
>         }
>     })
>     // More logic...
>     // Within your HTML, create a hidden <input> element containing your hiddenRef
>     return (
>        <!-- HTML code -->
>        <input ref={hiddenRef} type="hidden" name="someName" value="[]" />
>        <!-- More HTML code -->
>     )
>  }
>  ```
> To access your your React partial's data within your **view** after submitting the form, you can use the template provided below to access 
>  ```python
>  # Some logic within your Django view...
>  # Extract the stringified JSON data from your hidden <input element>
>  variable_raw = request.POST.get('someName', '[]')
>  try:
>      variable_processed = json.loads(topics_raw)
>  except json.JSONDecodeError:
>      variable_processed = []
>  # Some more logic using the data from your frontend!..
>  ```

## ML Environment
To use the ML Experiments environment, do the following
1. Go into the `ml_env` directory.
2. Run `poetry shell` to activate the environment
3. Within the activated environment run `poetry run jupyter notebook` to execute the Jupyter server.
4. Install additional packages within the poetry shell (e.g. `langchain`)
