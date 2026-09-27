import React, { useEffect, useState } from 'react'

const rates = ['input_rate_per_million', 'cached_input_rate_per_million', 'output_rate_per_million', 'rate_per_minute']
const label = key => key.replaceAll('_', ' ')
const initialForm = () => ({ kind: 'model', model_name: '', billing_unit: 'audio_duration', task_type: 'transcription', model_price_id: '', multiplier: '1', supersedes: '', effective_from: new Date(Date.now() + 3600000).toISOString().slice(0, 16), effective_to: '', activate_now: false, ...Object.fromEntries(rates.map(key => [key, ''])) })

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options })
  const body = await response.json().catch(() => ({ detail: `Request failed (HTTP ${response.status}). Reload and try again.` }))
  if (!response.ok) {
    const error = new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body))
    error.permission = response.status === 401 || response.status === 403
    throw error
  }
  return body
}

async function allRows(url, signal) {
  const rows = []
  while (url) {
    const page = await request(url, { signal })
    rows.push(...page.results)
    url = page.next
  }
  return rows
}

export default function PricingManagement({ api, canView, canManage, onPermissionError, onChanged }) {
  const [models, setModels] = useState([])
  const [tasks, setTasks] = useState([])
  const [readiness, setReadiness] = useState([])
  const [form, setForm] = useState(initialForm)
  const [preview, setPreview] = useState(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setModels([]); setTasks([]); setReadiness([])
    Promise.all([
      request(api.pricingReadiness, { signal: controller.signal }),
      canView ? allRows(api.modelPrices, controller.signal) : [],
      canView ? allRows(api.taskPricing, controller.signal) : [],
    ]).then(([state, prices, multipliers]) => {
      if (controller.signal.aborted) return
      setReadiness(state.tasks); setModels(prices); setTasks(multipliers)
    }).catch(err => {
      if (controller.signal.aborted) return
      if (err.permission) onPermissionError('Pricing access changed. Reload or sign in again.')
      else setError(err.message)
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [api, canView, revision, onPermissionError])

  function update(key, value) {
    setForm(current => ({ ...current, [key]: value }))
    setPreview(null); setConfirmed(false); setError(''); setMessage('')
  }

  function supersede(kind, record) {
    setForm({ ...initialForm(), ...Object.fromEntries(Object.entries(record).map(([key, value]) => [key, value ?? ''])), kind, supersedes: record.id, effective_from: initialForm().effective_from, effective_to: '' })
    setPreview(null); setConfirmed(false); setError(''); setMessage('')
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true); setError(''); setMessage('')
    try {
      let payload
      if (preview) {
        if (!confirmed) return
        payload = { confirmation_token: preview.confirmation_token }
      } else {
        payload = {
          activate_now: form.activate_now,
          effective_to: form.effective_to ? `${form.effective_to}:00Z` : null,
          ...(form.supersedes ? { supersedes: Number(form.supersedes) } : {}),
          ...(!form.activate_now ? { effective_from: `${form.effective_from}:00Z` } : {}),
        }
        if (form.kind === 'model') {
          Object.assign(payload, { provider: 'openai', currency: 'USD', model_name: form.model_name, billing_unit: form.billing_unit })
          for (const key of rates) payload[key] = form[key] || null
        } else Object.assign(payload, { task_type: form.task_type, model_price_id: Number(form.model_price_id), multiplier: form.multiplier })
      }
      const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value
      const result = await request(form.kind === 'model' ? api.modelPrices : api.taskPricing, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token || '' }, body: JSON.stringify(payload),
      })
      if (preview) {
        setMessage(`Saved ${form.kind} pricing #${result.record.id}.`)
        setPreview(null); setConfirmed(false); setForm(initialForm())
        setRevision(value => value + 1); onChanged()
      } else { setPreview(result); setConfirmed(false) }
    } catch (err) {
      setPreview(null); setConfirmed(false)
      if (err.permission) {
        setModels([]); setTasks([]); setReadiness([])
        onPermissionError('Pricing access changed. Reload or sign in again.')
      } else setError(err.message)
    } finally { setBusy(false) }
  }

  function history(kind, rows) {
    const columns = kind === 'model' ? ['model_name', 'billing_unit', 'currency', ...rates] : ['task_type', 'model_price_id', 'multiplier']
    return <div className="pricing-history"><table><thead><tr>{['id', ...columns, 'effective_from', 'effective_to', ...(canManage ? ['action'] : [])].map(key => <th key={key}>{label(key)}</th>)}</tr></thead><tbody>
      {rows.map(row => <tr key={row.id}>{['id', ...columns, 'effective_from', 'effective_to'].map(key => <td key={key}>{row[key] ?? (key === 'effective_to' ? 'Open-ended' : '—')}</td>)}
        {canManage && <td>{row.effective_to == null && <button type="button" disabled={busy} onClick={() => supersede(kind, row)}>Supersede #{row.id}</button>}</td>}
      </tr>)}
    </tbody></table>{!rows.length && <p>No pricing records.</p>}</div>
  }

  return <section className="pricing-management" aria-labelledby="pricing-heading">
    <h2 id="pricing-heading">Pricing administration</h2>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <h3>Configured model readiness</h3>
    <button type="button" disabled={busy || loading} onClick={() => { setError(''); setRevision(value => value + 1) }}>Refresh pricing</button>
    {loading ? <p role="status">Loading pricing…</p> : <ul>{readiness.map(row => <li key={row.task_type}>{label(row.task_type)} | {row.model_name} | {row.ready ? 'Pricing active' : `Not ready: ${row.error}`}</li>)}</ul>}
    {canView ? <><h3>Model prices: active, scheduled, and historical (UTC)</h3>{history('model', models)}<h3>Task multipliers: active, scheduled, and historical (UTC)</h3>{history('task', tasks)}</> : <p>Pricing history requires view_all_usage. You can submit changes and preview their affected records using IDs.</p>}
    {canManage && <form onSubmit={submit}>
      <h3>Add or supersede pricing</h3>
      <fieldset disabled={busy} className="usage-filters">
        <label>Record type<select value={form.kind} onChange={event => { setForm({ ...initialForm(), kind: event.target.value }); setPreview(null); setConfirmed(false) }}><option value="model">Model price</option><option value="task">Task multiplier</option></select></label>
        <label>Supersede record ID (optional)<input type="number" min="1" value={form.supersedes} onChange={event => update('supersedes', event.target.value)} /></label>
        {form.kind === 'model' ? <>
          <label>Model name<input required value={form.model_name} onChange={event => update('model_name', event.target.value)} /></label>
          <label>Billing unit<select value={form.billing_unit} onChange={event => { update('billing_unit', event.target.value); for (const key of rates) update(key, '') }}><option value="audio_duration">Audio duration (per minute)</option><option value="text_tokens">Text tokens (per million)</option></select></label>
          {(form.billing_unit === 'audio_duration' ? ['rate_per_minute'] : rates.slice(0, 3)).map(key => <label key={key}>{label(key)} (USD)<input type="number" step="any" min="0" required={key !== 'cached_input_rate_per_million'} value={form[key]} onChange={event => update(key, event.target.value)} /></label>)}
        </> : <>
          <label>Task<select value={form.task_type} onChange={event => update('task_type', event.target.value)}>{['transcription', 'summary', 'tagging'].map(task => <option key={task}>{task}</option>)}</select></label>
          <label>Model price ID<input required type="number" min="1" value={form.model_price_id} onChange={event => update('model_price_id', event.target.value)} /></label>
          <label>Multiplier<input required type="number" min="0.000001" step="any" value={form.multiplier} onChange={event => update('multiplier', event.target.value)} /></label>
        </>}
        <label><span>Immediate activation</span><input type="checkbox" checked={form.activate_now} onChange={event => update('activate_now', event.target.checked)} /></label>
        {!form.activate_now && <label>Effective from (UTC)<input required type="datetime-local" value={form.effective_from} onChange={event => update('effective_from', event.target.value)} /></label>}
        <label>Effective to (UTC, optional)<input type="datetime-local" value={form.effective_to} onChange={event => update('effective_to', event.target.value)} /></label>
      </fieldset>
      {preview && <div className="pricing-preview"><h3>Confirm proposed change</h3><p>{preview.warning}</p>
        <pre>{JSON.stringify({ proposed_record: preview.record, records_to_close: preview.closes }, null, 2)}</pre>
        <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} /> I confirm this pricing change and the effective periods shown above.</label>
      </div>}
      <button disabled={busy || (preview && !confirmed)} type="submit">{busy ? 'Working…' : preview ? 'Confirm and save pricing' : 'Preview change'}</button>
    </form>}
  </section>
}
