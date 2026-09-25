import React, { useMemo } from 'react'
import ReactDOM from 'react-dom/client'
import { getInitialData } from './utils/getInitialData'

export default function Usage() {
  const initialData = useMemo(() => getInitialData('initial-payload-usage'), [])
  return (
    <section aria-labelledby="usage-heading">
      <h2 id="usage-heading">Usage</h2>
      <p>The usage dashboard is coming soon.</p>
      <p>Reporting timezone: {initialData.defaults?.timezone || 'UTC'}</p>
    </section>
  )
}

const mount = document.getElementById('usage-root')
if (mount) ReactDOM.createRoot(mount).render(<Usage />)
