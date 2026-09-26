import React, { useCallback, useEffect, useMemo, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { getInitialData } from './utils/getInitialData'
import './usage.css'

const tasks = { transcription: 'Transcription', summary: 'Summaries', tagging: 'Tagging' }
const statuses = ['succeeded', 'pending', 'reconciliation_required', 'failed', 'simulated']
const label = value => value.replaceAll('_', ' ')
const date = value => value ? new Date(value).toLocaleString(undefined, { timeZone: 'UTC' }) : 'Open-ended'
const money = (value, currency = 'USD') => value == null ? 'Not finalized' : new Intl.NumberFormat(undefined, {
  style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 10,
}).format(Number(value))

async function fetchJson(url, signal) {
  const response = await fetch(url, { credentials: 'same-origin', signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    const error = new Error(response.status === 403 || response.status === 401
      ? 'Your access has changed or your session has expired. Sign in again or reload this page.'
      : `Unable to load usage (HTTP ${response.status}). Please try again.`)
    error.permission = response.status === 403 || response.status === 401
    throw error
  }
  return response.json()
}

function Table({ headings, children }) {
  return <div className="usage-table-scroll"><table><thead><tr>{headings.map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>
}

function Report({ api, filters, privileged, users, onPermissionError }) {
  const [page, setPage] = useState(1)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== ''))
    const eventsParams = new URLSearchParams(params)
    eventsParams.set('page', page)
    eventsParams.set('page_size', 20)
    Promise.all([
      fetchJson(`${api.summary}?${params}`, controller.signal),
      fetchJson(`${api.events}?${eventsParams}`, controller.signal),
    ]).then(([summary, events]) => {
      if (controller.signal.aborted) return
      if (privileged && !Array.isArray(summary.pricing_periods)) {
        onPermissionError('Your reporting permissions have changed. Reload this page to continue with your current access.')
        return
      }
      setResult({ summary, events })
      setLoading(false)
    }).catch(err => {
      if (controller.signal.aborted) return
      setResult(null)
      setLoading(false)
      if (err.permission) onPermissionError(err.message)
      else setError(err.message)
    })
    return () => controller.abort()
  }, [api, filters, page, attempt, privileged, onPermissionError])

  function navigate(nextPage) {
    setResult(null)
    setLoading(true)
    setError('')
    setPage(nextPage)
  }
  if (loading) return <p role="status">Loading usage…</p>
  if (error) return <div role="alert"><p>{error}</p><button onClick={() => { setError(''); setLoading(true); setAttempt(attempt + 1) }}>Retry</button></div>
  if (!result) return null
  const { summary, events } = result
  const username = id => users.find(user => user.id === id)?.username || `User ${id}`
  const currencies = summary.totals.length ? summary.totals : [{ currency: 'USD', billed_cost: '0', base_cost: '0', event_count: 0 }]
  return <>
    <p className="usage-period">{summary.period.month} · {date(summary.period.start)} through {date(summary.period.end)} UTC (end exclusive)</p>
    <div className="usage-cards">
      {currencies.map(total => <article key={total.currency}><h3>Total charged · {total.currency}</h3><strong>{money(total.billed_cost, total.currency)}</strong><p>{total.event_count} completed events</p>{privileged && <p>Base cost: {money(total.base_cost, total.currency)}</p>}</article>)}
    </div>
    <p>Charges include completed usage only. Pending and reconciliation events have no finalized charge.</p>
    {privileged && <div className="usage-counts" aria-label="Event status counts">{statuses.map(status => <span key={status}>{label(status)}: <b>{summary.status_counts.find(row => row.status === status)?.event_count || 0}</b></span>)}</div>}
    <h3>By task</h3>
    <Table headings={['Task', 'Currency', 'Events', ...(privileged ? ['Base cost'] : []), 'Charged']}>
      {Object.entries(tasks).flatMap(([task, title]) => {
        const rows = summary.tasks.filter(row => row.task_type === task)
        return (rows.length ? rows : [{ currency: 'USD', event_count: 0, base_cost: '0', billed_cost: '0' }]).map(row => <tr key={`${task}-${row.currency}`}><td>{title}</td><td>{row.currency}</td><td>{row.event_count}</td>{privileged && <td>{money(row.base_cost, row.currency)}</td>}<td>{money(row.billed_cost, row.currency)}</td></tr>)
      })}
    </Table>
    {privileged && summary.scope.kind === 'organization' && <><h3>By user</h3>{summary.users.length ? <Table headings={['User', 'Currency', 'Events', 'Base cost', 'Charged']}>
      {summary.users.map(row => <tr key={`${row.user_id}-${row.currency}`}><td>{username(row.user_id)}</td><td>{row.currency}</td><td>{row.event_count}</td><td>{money(row.base_cost, row.currency)}</td><td>{money(row.billed_cost, row.currency)}</td></tr>)}
    </Table> : <p>No completed usage for this selection.</p>}</>}
    {privileged && <><h3>Applied pricing periods</h3><p>Historical rates and multipliers associated with these completed events.</p>
      {summary.pricing_periods.length ? <Table headings={['Task / model', 'Effective periods (UTC)', 'Rates', 'Multiplier', 'Events', 'Base cost', 'Charged']}>
        {summary.pricing_periods.map((row, index) => <tr key={index}>
          <td>{tasks[row.task_type]}<br />{row.provider} / {row.model_name}<br />{label(row.billing_unit)}</td>
          <td>Model: {date(row.model_price_effective_from)} – {date(row.model_price_effective_to)}<br />Task: {date(row.task_pricing_effective_from)} – {date(row.task_pricing_effective_to)}</td>
          <td>{row.billing_unit === 'audio_duration' ? `${money(row.rate_per_minute, row.currency)} / minute` : <>Per million tokens:<br />Input: {money(row.input_rate_per_million, row.currency)}<br />Cached: {row.cached_input_rate_per_million == null ? 'Not configured' : money(row.cached_input_rate_per_million, row.currency)}<br />Output: {money(row.output_rate_per_million, row.currency)}</>}</td>
          <td>{Number(row.multiplier)}×</td><td>{row.event_count}</td><td>{money(row.base_cost, row.currency)}</td><td>{money(row.billed_cost, row.currency)}</td>
        </tr>)}
      </Table> : <p>No applied pricing periods for this selection.</p>}</>}
    <h3>Usage events</h3>
    {!events.count ? <p>No usage events match this selection.</p> : <>
      <Table headings={['When (UTC)', ...(privileged ? ['User'] : []), 'Task / model', 'Status', 'Charged', 'Details']}>
        {events.results.map(event => <tr key={event.id}>
          <td>{date(event.occurred_at)}</td>{privileged && <td>{username(event.user_id)}</td>}<td>{tasks[event.task_type]}<br />{event.model_name}</td><td>{label(event.status)}</td><td>{money(event.billed_cost, event.currency)}</td>
          <td><details><summary>Event #{event.id}</summary><dl>
            <dt>Source</dt><dd>{event.usage_source}</dd>
            {event.billing_unit === 'audio_duration' ? <><dt>Audio seconds</dt><dd>{event.audio_duration_seconds ?? 'Unknown'}</dd></> : <><dt>Uncached input tokens</dt><dd>{event.input_tokens ?? 'Unknown'}</dd><dt>Cached input tokens</dt><dd>{event.cached_input_tokens ?? 'Unknown'}</dd><dt>Output tokens</dt><dd>{event.output_tokens ?? 'Unknown'}</dd></>}
            {privileged && <><dt>Base cost</dt><dd>{money(event.base_cost, event.currency)}</dd><dt>Multiplier</dt><dd>{Number(event.multiplier)}×</dd><dt>Provider request</dt><dd>{event.provider_request_id || 'Unavailable'}</dd></>}
            {['transcript_id', 'summary_id', 'tag_id', 'transcription_chunk_id'].filter(key => event[key] != null).map(key => <React.Fragment key={key}><dt>{label(key)}</dt><dd>{event[key]}</dd></React.Fragment>)}
          </dl></details></td>
        </tr>)}
      </Table>
      <nav className="usage-pagination" aria-label="Usage event pages"><button disabled={!events.previous} onClick={() => navigate(page - 1)}>Previous</button><span>Page {page} of {Math.ceil(events.count / 20)} · {events.count} events</span><button disabled={!events.next} onClick={() => navigate(page + 1)}>Next</button></nav>
    </>}
  </>
}

export default function Usage() {
  const initialData = useMemo(() => getInitialData('initial-payload-usage'), [])
  const privileged = Boolean(initialData.capabilities?.canViewAllUsage)
  const [filters, setFilters] = useState({ month: new Date().toISOString().slice(0, 7), user_id: '', task_type: '', model_name: '', status: '' })
  const [model, setModel] = useState('')
  const [users, setUsers] = useState([])
  const [accessError, setAccessError] = useState('')
  const [usersError, setUsersError] = useState('')
  const handlePermissionError = useCallback(message => {
    setUsers([])
    setAccessError(message)
  }, [])
  useEffect(() => {
    if (!privileged || accessError) return
    const controller = new AbortController()
    async function loadUsers() {
      const rows = []
      let url = initialData.apiUrls.users
      while (url) {
        const response = await fetchJson(url, controller.signal)
        rows.push(...response.results)
        url = response.next
      }
      if (!controller.signal.aborted) setUsers(rows)
    }
    loadUsers().catch(err => {
      if (controller.signal.aborted) return
      setUsers([])
      if (err.permission) handlePermissionError(err.message)
      else setUsersError(err.message)
    })
    return () => controller.abort()
  }, [privileged, initialData, accessError, handlePermissionError])
  function update(name, value) { setFilters(current => ({ ...current, [name]: value })) }
  return (
    <section className="usage-dashboard" aria-labelledby="usage-heading">
      <h2 id="usage-heading">Usage</h2>
      {accessError ? <p role="alert">{accessError}</p> : <>
        <p>{privileged ? 'Organization usage and charges' : 'Your usage and charges'} · Calendar months in UTC</p>
        <form className="usage-filters" onSubmit={event => { event.preventDefault(); update('model_name', model.trim()) }}>
          <label>Month<input type="month" required value={filters.month} onChange={event => { if (event.target.value) update('month', event.target.value) }} /></label>
          {privileged && <><label>User<select value={filters.user_id} onChange={event => update('user_id', event.target.value)}><option value="">All users</option>{users.map(user => <option key={user.id} value={user.id}>{user.username}</option>)}</select></label>
            <label>Task<select value={filters.task_type} onChange={event => update('task_type', event.target.value)}><option value="">All tasks</option>{Object.entries(tasks).map(([value, title]) => <option key={value} value={value}>{title}</option>)}</select></label>
            <label>Model (exact name)<input value={model} placeholder="All models" onChange={event => setModel(event.target.value)} /></label><button type="submit">Apply model</button>
            <label>Status<select value={filters.status} onChange={event => update('status', event.target.value)}><option value="">All statuses</option>{statuses.map(status => <option key={status} value={status}>{label(status)}</option>)}</select></label>
          </>}
        </form>
        {usersError && <p role="alert">User names could not be loaded. {usersError}</p>}
        <Report key={JSON.stringify(filters)} api={initialData.apiUrls} filters={filters} privileged={privileged} users={users} onPermissionError={handlePermissionError} />
      </>}
    </section>
  )
}

const mount = document.getElementById('usage-root')
if (mount) ReactDOM.createRoot(mount).render(<Usage />)
