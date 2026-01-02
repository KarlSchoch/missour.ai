import React, {useState, useMemo} from 'react'
import ReactDOM from 'react-dom/client'
import { getCsrfToken } from './utils/csrf'

function getInitialData() {
  const el = document.getElementById('initial-payload')
  return el ? JSON.parse(el.textContent) : {}
}

function App() {
  const init = React.useMemo(getInitialData, [])
  const [topics, setTopics] = React.useState(null)

  const reloadTopics = React.useCallback(async () => {
    const url = init?.apiUrls?.topics
    if (!url) return
    const r = await fetch(url, { credentials: 'include' })
    const data = await r.json()
    setTopics(data)
  }, [init?.apiUrls?.topics])

  console.log("topics", topics)

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
      <h2>Add Topic</h2>
    </div>
  )
}

const mount = document.getElementById('view-topics-root')
if (mount) ReactDOM.createRoot(mount).render(<App />)
else console.error('#view-topics-root not found')
