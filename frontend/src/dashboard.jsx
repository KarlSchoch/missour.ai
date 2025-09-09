import React from 'react'
import ReactDOM from 'react-dom/client'

function getInitialData() {
    const el = document.getElementById('initial-payload');
    return el ? JSON.parse(el.textContent) : {}
}

function getCsrfToken() {
    return document.cookie.split('; ')
      .find(row => row.startsWith('csrftoken='))?.split('=')[1]
}

function App() {
    const init = React.useMemo(getInitialData, []);
    const [status, setStatus] = React.useState(null);
    const [items, setItems] = React.useState([])

    React.useEffect(() => {
        fetch(getInitialData.apiUrls.ping, {credentials: 'include' })
          .then(r => r.json()).then(setStatus).catch(console.error)
    }, init.apiUrls.ping);

    const reloadItems = React.useCallback(async () => {
        const r = await fetch(init.apiUrls.items, { credentials: 'include' });
        setItems(await r.json())
    }, init.apiUrls.items)

    async function addItem() {
        await fetch(init.apiUrls.items, {
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
            <ul>
                {
                    items.map(i => <li key={i.id}>{i.name}</li>)
                }
            </ul>
        </div>
    )
}

ReactDOM.createRoot(document.getElementById('dashboard-root')).render(<App />)