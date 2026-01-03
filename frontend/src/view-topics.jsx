import React, {useState, useMemo} from 'react'
import ReactDOM from 'react-dom/client'
import { getCsrfToken } from './utils/csrf'

function getInitialData() {
  const el = document.getElementById('initial-payload')
  return el ? JSON.parse(el.textContent) : {}
}

const blankTopic = () => ({ name: "", description: "" });

function App() {
  // Extract initial data that contains information on relevant APIs
  const init = React.useMemo(getInitialData, [])
  // Instantiate existing Topics
  const [topics, setTopics] = React.useState(null)
  // Instantiate array of new topics to be created
  const [newTopics, setNewTopics] = useState([blankTopic()])

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

  console.log("topics", topics)
  console.log("newTopics", newTopics)

  React.useEffect(() => { reloadTopics() }, [reloadTopics])

  // async function addItem() {
  //   const url = init?.apiUrls?.items
  //   if (!url) return
  //   await fetch(url, {
  //     method: 'POST',
  //     headers: {
  //       'Content-Type': 'application/json',
  //       'X-CSRFToken': getCsrfToken(),
  //     },
  //     credentials: 'include',
  //     body: JSON.stringify({ name: `Item ${Date.now()}` }),
  //   })
  //   reloadItems()
  // }

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
      <h2>Create New Topics</h2>
      <form>
        {newTopics.map((t, idx) => (
          <div key={idx}>
            <div>
              <label>
                Name:
                <input
                  value={t.name}
                  onChange={(e) => updateTopic(idx, "name", e.target.value)}
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
                  placeholder="Optional description..."
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
          <br />
          <button type='submit'>Submit</button>
        </div>
      </form>
    </div>
  )
}

const mount = document.getElementById('view-topics-root')
if (mount) ReactDOM.createRoot(mount).render(<App />)
else console.error('#view-topics-root not found')
