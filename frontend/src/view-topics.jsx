import React, {useState, useReducer} from 'react'
import ReactDOM from 'react-dom/client'
import { getCsrfToken } from './utils/csrf'
import { 
  handleAddTopic,
  handleRemoveTopic,
  handleUpdateTopic
 } from './add-topics/add-topics-event-handlers';

import { 
  AddTopicsContext,
  AddTopicsDispatchContext 
} from './add-topics/add-topics-context';

function getInitialData() {
  const el = document.getElementById('initial-payload')
  return el ? JSON.parse(el.textContent) : {}
}

const blankTopic = () => ({ topic: "", description: "" });

function App() {
  // Extract initial data that contains information on relevant APIs
  const init = React.useMemo(getInitialData, [])
  // Instantiate existing Topics
  const [topics, setTopics] = React.useState(null)
  // Instantiate array of new topics to be created
  const [newTopics, setNewTopics] = useState([blankTopic()])
  // Create state variables for providing user feedback
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Function for adding new topic fields to form
  function addTopic() {
    setNewTopics((prev) => [...prev, blankTopic()]);
  }

  // Function for updating elements of newTopics array based on user input
  function updateTopic(index, field, value) {
    setNewTopics((prev) => 
      prev.map((t, i) => (i === index ? { ...t, [field]: value } : t))
    );
  }

  // Function for removing topics
  function removeNewTopic(index) {
    setNewTopics((prev) => {
      if (prev.length === 1) return prev 
      return prev.filter((_, i) => i !== index);
    });
  }

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
          // Reload the list of topics show on the page and set up a new form
          setNewTopics([blankTopic()]);
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
        {newTopics.map((t, idx) => (
          <div key={idx}>
            <div>
              <label>
                Name:
                <input
                  value={t.topic}
                  onChange={(e) => updateTopic(idx, "topic", e.target.value)}
                  placeholder="e.g., Supply Chain Risk"
                />
              </label>
            </div>

            <div>
              <label>
                Description:
                <textarea
                  value={t.description}
                  onChange={(e) => updateTopic(idx, "description", e.target.value)}
                  placeholder="Optional description of the topic..."
                />
              </label>
            </div>

            <button type="button" onClick={() => removeNewTopic(idx)}>
              Remove
            </button>
            <hr />
          </div>
        ))}
        <div>
          <button type="button" onClick={addTopic}>
            + Add another topic
          </button>
          <hr />
          <button type='submit' onClick={onSubmit} disabled={isSubmitting} >
            {isSubmitting ? "Submitting..." : "Submit"}
          </button>
        </div>
        {error && <p style={{ color: "crimson" }}>{error}</p>}
      </form>
    </div>
  )
}

const mount = document.getElementById('view-topics-root')
if (mount) ReactDOM.createRoot(mount).render(<App />)
else console.error('#view-topics-root not found')
