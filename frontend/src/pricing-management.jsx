import React, { useEffect, useState } from 'react'

const rates = ['input_rate_per_million', 'cached_input_rate_per_million', 'output_rate_per_million', 'rate_per_minute']
const label = key => key.replaceAll('_', ' ')
const initialForm = () => ({ kind: 'model', model_name: '', billing_unit: 'audio_duration', task_type: 'transcription', multiplier: '1', selected_supersedes: '', effective_from: new Date(Date.now() + 3600000).toISOString().slice(0, 16), effective_to: '', activate_now: false, ...Object.fromEntries(rates.map(key => [key, ''])) })
const currency = (value, code = 'USD') => new Intl.NumberFormat(undefined, { style: 'currency', currency: code, minimumFractionDigits: 2, maximumFractionDigits: 10 }).format(Number(value))
const timestamp = value => value ? `${new Date(value).toLocaleString(undefined, { timeZone: 'UTC' })} UTC` : 'Open-ended'
const modelOptionLabel = option => `${option.model_name}${option.configured_for_task ? ' (configured)' : ''}`

function rateLines(row, factor = 1) {
  if (row.billing_unit === 'audio_duration') return `${currency(Number(row.rate_per_minute) * factor, row.currency)}/minute`
  const values = [
    ['Input', row.input_rate_per_million],
    ['Cached input', row.cached_input_rate_per_million],
    ['Output', row.output_rate_per_million],
  ]
  return values.map(([name, value]) => <span key={name}>{name}: {value == null ? 'Not configured' : `${currency(Number(value) * factor, row.currency)}/1M tokens`}</span>)
}

function pricingLines(row, customer = false) {
  if (!row.ready) return 'Unavailable'
  return rateLines(row, customer ? Number(row.multiplier) : 1)
}

function PreviewTables({ preview, kind }) {
  const record = preview.record
  const impacts = preview.task_pricing_impacts || []
  return <div className="pricing-preview-tables">
    <h4>Proposed {kind === 'model' ? 'model price' : 'task multiplier'}</h4>
    <div className="pricing-table-scroll"><table><thead><tr>
      {(kind === 'model'
        ? ['Model', 'Billing unit', 'Base pricing', 'Effective from', 'Effective to']
        : ['Task', 'Model price', 'Multiplier', 'Effective from', 'Effective to']
      ).map(heading => <th key={heading}>{heading}</th>)}
    </tr></thead><tbody><tr>{kind === 'model' ? <>
      <td>{record.model_name}</td><td>{label(record.billing_unit)}</td><td className="pricing-lines">{rateLines(record)}</td><td>{timestamp(record.effective_from)}</td><td>{timestamp(record.effective_to)}</td>
    </> : <>
      <td>{label(record.task_type)}</td><td>{impacts[0]?.model_name || `Model price #${record.model_price_id}`}</td><td>{Number(record.multiplier)}×</td><td>{timestamp(record.effective_from)}</td><td>{timestamp(record.effective_to)}</td>
    </>}</tr></tbody></table></div>

    <h4>Task pricing impacts</h4>
    {impacts.length ? <div className="pricing-table-scroll"><table><thead><tr><th>Task</th><th>Model</th><th>Current customer pricing</th><th>Proposed customer pricing</th><th>Multiplier</th><th>Status</th></tr></thead><tbody>
      {impacts.map(item => <tr key={`${item.task_type}-${item.model_name}`}>
        <td>{label(item.task_type)}</td><td>{item.model_name}</td>
        <td className="pricing-lines">{item.current_customer_pricing ? rateLines(item.current_customer_pricing) : 'Not configured'}</td>
        <td className="pricing-lines">{rateLines(item.proposed_customer_pricing)}</td>
        <td>{Number(item.multiplier)}×</td>
        <td><span className={item.ready ? 'pricing-status-ready' : 'pricing-status-error'}>{item.ready ? 'Ready after change' : 'Not ready'}</span>{item.error && <small>{item.error}</small>}</td>
      </tr>)}
    </tbody></table></div> : <p>No task pricing currently uses this model price. The model price can be created, but no task will be billable through it until task pricing is configured.</p>}
  </div>
}

function apiErrorMessage(body) {
  if (typeof body?.detail === 'string') return body.detail
  if (Array.isArray(body)) return body.join(' ')
  if (body && typeof body === 'object') return Object.entries(body).map(([field, messages]) => `${label(field)}: ${Array.isArray(messages) ? messages.join(' ') : messages}`).join(' ')
  return 'The request could not be completed.'
}

async function request(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options })
  const body = await response.json().catch(() => ({ detail: `Request failed (HTTP ${response.status}). Reload and try again.` }))
  if (!response.ok) {
    const error = new Error(apiErrorMessage(body))
    error.permission = response.status === 401 || response.status === 403
    error.body = body
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
  const [candidateChoice, setCandidateChoice] = useState(null)
  const [modelOptions, setModelOptions] = useState([])
  const [modelOptionConflicts, setModelOptionConflicts] = useState([])
  const [modelOptionsLoading, setModelOptionsLoading] = useState(false)
  const [modelOptionsLoaded, setModelOptionsLoaded] = useState(false)
  const [modelOptionsError, setModelOptionsError] = useState('')
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

  useEffect(() => {
    if (form.kind !== 'task') {
      setModelOptions([]); setModelOptionConflicts([]); setModelOptionsLoading(false); setModelOptionsLoaded(false); setModelOptionsError('')
      return
    }
    if (!api.pricingModelOptions) {
      setModelOptions([]); setModelOptionConflicts([]); setModelOptionsLoading(false); setModelOptionsLoaded(false)
      setModelOptionsError('Model choices are unavailable because this page has an older configuration. Reload the page and try again.')
      return
    }
    const controller = new AbortController()
    const params = new URLSearchParams({ task_type: form.task_type })
    if (!form.activate_now) params.set('at', `${form.effective_from}:00Z`)
    setModelOptions([]); setModelOptionConflicts([]); setModelOptionsLoading(true); setModelOptionsLoaded(false); setModelOptionsError('')
    request(`${api.pricingModelOptions}?${params}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      setModelOptions(result.options)
      setModelOptionConflicts(result.conflicts)
      setModelOptionsLoaded(true)
      setForm(current => {
        if (current.kind !== 'task' || result.options.some(option => option.model_name === current.model_name)) return current
        const preferred = result.options.find(option => option.configured_for_task) || result.options[0]
        return { ...current, model_name: preferred?.model_name || '' }
      })
    }).catch(err => {
      if (controller.signal.aborted) return
      setModelOptions([]); setModelOptionConflicts([]); setModelOptionsLoaded(false)
      if (err.permission) onPermissionError('Pricing access changed. Reload or sign in again.')
      else setModelOptionsError(`Model choices could not be loaded. ${err.message}`)
    }).finally(() => { if (!controller.signal.aborted) setModelOptionsLoading(false) })
    return () => controller.abort()
  }, [api, form.kind, form.task_type, form.activate_now, form.effective_from, revision, onPermissionError])

  function update(key, value) {
    setForm(current => ({ ...current, [key]: value }))
    setPreview(null); setConfirmed(false); setCandidateChoice(null); setError(''); setMessage('')
  }

  function supersede(kind, record) {
    const modelName = kind === 'task' ? models.find(model => model.id === record.model_price_id)?.model_name || '' : record.model_name
    setForm({ ...initialForm(), ...Object.fromEntries(Object.entries(record).map(([key, value]) => [key, value ?? ''])), kind, model_name: modelName, selected_supersedes: record.id, effective_from: initialForm().effective_from, effective_to: '' })
    setPreview(null); setConfirmed(false); setCandidateChoice(null); setError(''); setMessage('')
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
          ...(form.selected_supersedes ? { selected_supersedes: Number(form.selected_supersedes) } : {}),
          ...(!form.activate_now ? { effective_from: `${form.effective_from}:00Z` } : {}),
        }
        if (form.kind === 'model') {
          Object.assign(payload, { provider: 'openai', currency: 'USD', model_name: form.model_name, billing_unit: form.billing_unit })
          for (const key of rates) payload[key] = form[key] || null
        } else Object.assign(payload, { task_type: form.task_type, model_name: form.model_name, multiplier: form.multiplier })
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
      } else if (['selection_required', 'configuration_conflict'].includes(err.body?.code)) {
        setCandidateChoice(err.body)
        setError(err.body.detail)
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
    <h3>Current pricing configuration</h3>
    <button type="button" disabled={busy || loading} onClick={() => { setError(''); setRevision(value => value + 1) }}>Refresh pricing</button>
    {loading ? <p role="status">Loading pricing…</p> : <div className="pricing-current"><table><thead><tr><th>Task</th><th>Model</th><th>Base pricing</th><th>Multiplier</th><th>Customer pricing</th><th>Status</th></tr></thead><tbody>
      {readiness.map(row => <tr key={row.task_type}><td>{label(row.task_type)}</td><td>{row.model_name}</td><td className="pricing-lines">{pricingLines(row)}</td><td>{row.ready ? `${Number(row.multiplier)}×` : '—'}</td><td className="pricing-lines">{pricingLines(row, true)}</td><td><span className={row.ready ? 'pricing-status-ready' : 'pricing-status-error'}>{row.ready ? 'Ready' : 'Not ready'}</span>{!row.ready && <small>{row.error}</small>}</td></tr>)}
    </tbody></table></div>}
    {canManage && <form onSubmit={submit}>
      <h3>Add or supersede pricing</h3>
      <fieldset disabled={busy} className="usage-filters">
        <label>Record type<select value={form.kind} onChange={event => { const kind = event.target.value; setForm({ ...initialForm(), kind }); setModelOptionsLoading(kind === 'task'); setModelOptionsLoaded(false); setModelOptionsError(''); setPreview(null); setConfirmed(false); setCandidateChoice(null); setError('') }}><option value="model">Model price</option><option value="task">Task multiplier</option></select></label>
        {form.kind === 'model' ? <>
          <label>Model name<input required value={form.model_name} onChange={event => update('model_name', event.target.value)} /></label>
          <label>Billing unit<select value={form.billing_unit} onChange={event => { update('billing_unit', event.target.value); for (const key of rates) update(key, '') }}><option value="audio_duration">Audio duration (per minute)</option><option value="text_tokens">Text tokens (per million)</option></select></label>
          {(form.billing_unit === 'audio_duration' ? ['rate_per_minute'] : rates.slice(0, 3)).map(key => <label key={key}>{label(key)} (USD)<input type="number" step="any" min="0" required={key !== 'cached_input_rate_per_million'} value={form[key]} onChange={event => update(key, event.target.value)} /></label>)}
        </> : <>
          <label>Task<select value={form.task_type} onChange={event => { setForm(current => ({ ...current, task_type: event.target.value, model_name: '', selected_supersedes: '' })); setModelOptionsLoading(true); setModelOptionsLoaded(false); setModelOptionsError(''); setPreview(null); setCandidateChoice(null) }}>{['transcription', 'summary', 'tagging'].map(task => <option key={task}>{task}</option>)}</select></label>
          <label>Model<select required disabled={modelOptionsLoading || !modelOptions.length} value={form.model_name} onChange={event => update('model_name', event.target.value)}><option value="">{modelOptionsLoading ? 'Loading compatible models…' : 'Select a model'}</option>{modelOptions.map(option => <option key={option.id} value={option.model_name}>{modelOptionLabel(option)}</option>)}</select></label>
          <label>Multiplier<input required type="number" min="0.000001" step="any" value={form.multiplier} onChange={event => update('multiplier', event.target.value)} /></label>
        </>}
        <label><span>Immediate activation</span><input type="checkbox" checked={form.activate_now} onChange={event => update('activate_now', event.target.checked)} /></label>
        {!form.activate_now && <label>Effective from (UTC)<input required type="datetime-local" value={form.effective_from} onChange={event => update('effective_from', event.target.value)} /></label>}
        <label>Effective to (UTC, optional)<input type="datetime-local" value={form.effective_to} onChange={event => update('effective_to', event.target.value)} /></label>
      </fieldset>
      {error && <p role="alert" className="pricing-form-message">Pricing preview could not be created. {error}</p>}
      {message && <p role="status" className="pricing-form-message">{message}</p>}
      {form.kind === 'task' && modelOptionsError && <p role="alert">{modelOptionsError}</p>}
      {form.kind === 'task' && modelOptionsLoaded && !modelOptions.length && !modelOptionConflicts.length && <p role="alert">No compatible model prices apply to this task at the selected activation time.</p>}
      {form.kind === 'task' && modelOptionConflicts.length > 0 && <div className="pricing-candidates"><h4>Conflicting model prices</h4><p>These models have multiple applicable price records and cannot be selected until their pricing periods are corrected.</p>{modelOptionConflicts.map(item => <p key={item.model_name}><b>{item.model_name}</b>: {item.records.map(record => `#${record.id}`).join(', ')}</p>)}</div>}
      {form.kind === 'task' && form.model_name && modelOptions.some(option => option.model_name === form.model_name) && <div className="pricing-option-summary"><b>Selected base pricing:</b> <span className="pricing-lines">{rateLines(modelOptions.find(option => option.model_name === form.model_name))}</span></div>}
      {candidateChoice && <div className="pricing-candidates">
        <h4>{candidateChoice.code === 'selection_required' ? 'Select a pricing record' : 'Conflicting pricing records'}</h4>
        <p>{candidateChoice.detail}</p>
        {candidateChoice.candidates.map(record => <label key={record.id}>
          {candidateChoice.code === 'selection_required' && <input type="radio" name="pricing-candidate" checked={Number(form.selected_supersedes) === record.id} onChange={() => setForm(current => ({ ...current, selected_supersedes: record.id }))} />}
          <span><b>Record #{record.id}</b> · {record.model_name || record.task_type} · {record.billing_unit || `model price #${record.model_price_id}`} · {record.effective_from} to {record.effective_to || 'open-ended'}</span>
        </label>)}
      </div>}
      {preview && <div className="pricing-preview"><h3>Confirm proposed change</h3><p>{preview.warning}</p>
        <PreviewTables preview={preview} kind={form.kind} />
        <label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} /> I confirm this pricing change and the effective periods shown above.</label>
      </div>}
      <button disabled={busy || (form.kind === 'task' && (!form.model_name || modelOptionsLoading)) || (preview && !confirmed) || candidateChoice?.code === 'configuration_conflict' || (candidateChoice?.code === 'selection_required' && !form.selected_supersedes)} type="submit">{busy ? 'Working…' : preview ? 'Confirm and save pricing' : 'Preview change'}</button>
    </form>}
    {canView ? <div className="pricing-history-sections">
      <details><summary>Model price history</summary><h3>Model prices: active, scheduled, and historical (UTC)</h3>{history('model', models)}</details>
      <details><summary>Task multiplier history</summary><h3>Task multipliers: active, scheduled, and historical (UTC)</h3>{history('task', tasks)}</details>
    </div> : <p>Pricing history requires view_all_usage. You can submit changes and preview their affected records using IDs.</p>}
  </section>
}
