import React from 'react'
import ReactDOM from 'react-dom/client'

function getInitialData() {
  const el = document.getElementById('initial-payload')
  return el ? JSON.parse(el.textContent) : {}
}

function getCsrfToken() {
  return document.cookie.split('; ')
    .find(row => row.startsWith('csrftoken='))?.split('=')[1]
}

function App() {
  const init = React.useMemo(getInitialData, [])
  const [status, setStatus] = React.useState(null)
  const [items, setItems] = React.useState([])

  React.useEffect(() => {
    const url = init?.apiUrls?.ping
    if (!url) return
    fetch(url, { credentials: 'include' })
      .then(r => r.json())
      .then(setStatus)
      .catch(e => console.error('ping failed:', e))
  }, [init?.apiUrls?.ping])

  const reloadItems = React.useCallback(async () => {
    const url = init?.apiUrls?.items
    if (!url) return
    const r = await fetch(url, { credentials: 'include' })
    setItems(await r.json())
  }, [init?.apiUrls?.items])

  React.useEffect(() => { reloadItems() }, [reloadItems])

  async function addItem() {
    const url = init?.apiUrls?.items
    if (!url) return
    await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      credentials: 'include',
      body: JSON.stringify({ name: `Item ${Date.now()}` }),
    })
    reloadItems()
  }

  return (
    <div style={{ padding: 16 }}>
      <pre>Ping: {JSON.stringify(status, null, 2)}</pre>
      <button onClick={addItem}>Add Items</button>
      <ul>{items.map(i => <li key={i.id}>{i.name}</li>)}</ul>
    </div>
  )
}

const mount = document.getElementById('dashboard-root')
if (mount) ReactDOM.createRoot(mount).render(<App />)
else console.error('#dashboard-root not found')
