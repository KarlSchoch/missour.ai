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
  // const [items, setItems] = React.useState([])

  // React.useEffect(() => {
  //   const url = init?.apiUrls?.topics // Update name of url
  //   if (!url) return
  //   fetch(url, { credentials: 'include' })
  //     .then(r => r.json())
  //     .then(console.log(r))
  //     .then(setTopics)
  //     .catch(e => console.error('topics failed:', e))
  // }, [init?.apiUrls?.topics])

  const reloadTopics = React.useCallback(async () => {
    const url = init?.apiUrls?.topics
    if (!url) return
    const r = await fetch(url, { credentials: 'include' })
    const data = await r.json()
    setTopics(data)
  }, [init?.apiUrls?.topics])

  // console.log("topics", topics)

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
      <h1>View Topics</h1>
      <ul>
        {
          (topics || []).map(t => 
            <li key={t.id ?? t.topic}>{t.topic ?? JSON.stringify(t)}</li>
          )
        }
      </ul>
    </div>
  )
}

const mount = document.getElementById('view-topics-root')
if (mount) ReactDOM.createRoot(mount).render(<App />)
else console.error('#view-topics-root not found')
