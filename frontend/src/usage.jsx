import React, { useMemo } from 'react'
import ReactDOM from 'react-dom/client'

import { getInitialData } from './utils/getInitialData'


export default function Usage() {
  const initialData = useMemo(
    () => getInitialData('initial-payload-usage'),
    [],
  )

  return (
    <section aria-labelledby="usage-heading">
      <h2 id="usage-heading">Usage</h2>
      <p>
        Usage reporting is ready. The dashboard will load data from the secured
        usage APIs in the next implementation phase.
      </p>
      <span hidden data-can-view-all-usage={String(
        Boolean(initialData?.capabilities?.canViewAllUsage)
      )} />
    </section>
  )
}


const mount = document.getElementById('usage-root')
if (mount) ReactDOM.createRoot(mount).render(<Usage />)
