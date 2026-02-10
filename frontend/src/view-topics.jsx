import React, {useState, useMemo, useReducer} from 'react'
import ReactDOM from 'react-dom/client'
import { getCsrfToken } from './utils/csrf'
import AddTopics from './add-topics/add-topics';
import addTopicsReducer from './add-topics/add-topics-reducer';
import { 
  AddTopicsContext,
  AddTopicsDispatchContext 
} from './add-topics/add-topics-context';

function getInitialData() {
  const el = document.getElementById('initial-payload')
  return el ? JSON.parse(el.textContent) : {}
}

function App() {
  // Extract initial data that contains information on relevant APIs
  const init = useMemo(getInitialData, [])
  // Instantiate existing Topics
  const [topics, setTopics] = useState(null)
  // Instantiate array of new topics to be created
  const [newTopics, dispatch] = useReducer(
    addTopicsReducer,
    [{ topic: "", description: "" }]
  )
  // Create state variables for providing user feedback
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const reloadTopics = React.useCallback(async () => {
    const url = init?.apiUrls?.topics
    if (!url) return
    const r = await fetch(url, { credentials: 'include' })
    const data = await r.json()
    setTopics(data)
  }, [init?.apiUrls?.topics])

  React.useEffect(() => { reloadTopics() }, [reloadTopics])

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const url = init?.apiUrls?.topics
    if (!url) return

    // Ensure new topics are valid
    const payloadTopics = newTopics.filter((t) => t.topic.length > 0)
    if (payloadTopics.length === 0) {
      setError("Add at least one topic before submitting.");
      setIsSubmitting(false);
      return;
    }
    
    // Iterate through newTopics (backend TopicSerializer accepts only a single topic)
    for (const t of payloadTopics) {
      // Create payload
      const payload = { 
        topic: t.topic.trim(),
        description: t.description.trim()
      }

      // Call backend create API
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
          },
          credentials: 'include',
          body: JSON.stringify(payload),
        })

        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || "Request failed");
        }
        if (res.ok) {
          // Reset the list of topics show on the page and set up a new form
          dispatch({
              type: 'reset',
          })
        }
      } catch (err) {
        setError(err.message || "Something went wrong.");
      } finally {
        setIsSubmitting(false);
        await reloadTopics();
      }
    }
  }

  return (
    <div>
      <h1>Topics</h1>
      <h2>Current Topics</h2>
      <ul>
        {
          (topics || []).map(t => 
            <li key={t.id ?? t.topic}>
              {t.topic ?? JSON.stringify(t)}{t.description ?? `: ${t.description}`}
            </li>
          )
        }
      </ul>
      <h2>Create New Topic(s)</h2>
      <form>
        <AddTopicsContext.Provider value={newTopics}>
          <AddTopicsDispatchContext value={dispatch}>
            <AddTopics />
          </AddTopicsDispatchContext>
        </AddTopicsContext.Provider>
        <hr />
        <button type='submit' onClick={onSubmit} disabled={isSubmitting} >
            {isSubmitting ? "Submitting..." : "Submit"}
        </button>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </form>
    </div>
  )
}

const mount = document.getElementById('view-topics-root')
if (mount) ReactDOM.createRoot(mount).render(<App />)
else console.error('#view-topics-root not found')
