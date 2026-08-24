import { useEffect, useState } from 'react'

import { getHealth, getReadiness } from './services/healthApi.js'

const loadingState = { kind: 'loading', label: 'Checking…' }

function StatusCard({ title, state }) {
  return (
    <article className="status-card">
      <div>
        <p className="status-card__label">{title}</p>
        <p className="status-card__detail">{state.detail}</p>
      </div>
      <span className={`status-badge status-badge--${state.kind}`}>
        {state.label}
      </span>
    </article>
  )
}

function App() {
  const [health, setHealth] = useState(loadingState)
  const [readiness, setReadiness] = useState(loadingState)

  useEffect(() => {
    let active = true

    getHealth()
      .then((result) => {
        if (active) {
          setHealth({
            kind: 'success',
            label: 'Healthy',
            detail: `${result.application} v${result.version}`,
          })
        }
      })
      .catch(() => {
        if (active) {
          setHealth({
            kind: 'error',
            label: 'Unavailable',
            detail: 'The backend health endpoint could not be reached.',
          })
        }
      })

    getReadiness()
      .then((result) => {
        if (active) {
          setReadiness({
            kind: result.status === 'ready' ? 'success' : 'warning',
            label: result.status === 'ready' ? 'Ready' : 'Not ready',
            detail:
              result.status === 'ready'
                ? 'MongoDB and Neo4j are reachable.'
                : 'One or more data services are unavailable.',
          })
        }
      })
      .catch(() => {
        if (active) {
          setReadiness({
            kind: 'error',
            label: 'Unavailable',
            detail: 'The backend readiness endpoint could not be reached.',
          })
        }
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">Repository intelligence</p>
        <h1>Understand code through structure and evidence.</h1>
        <p className="hero__copy">
          CodeGraph AI will combine repository knowledge graphs and semantic
          retrieval to answer questions and review changes with source-backed
          evidence.
        </p>
      </section>

      <section className="status-panel" aria-labelledby="system-status-title">
        <div className="status-panel__heading">
          <div>
            <p className="eyebrow">Foundation</p>
            <h2 id="system-status-title">System status</h2>
          </div>
          <p>Live checks from the FastAPI backend.</p>
        </div>
        <div className="status-grid">
          <StatusCard title="Backend" state={health} />
          <StatusCard title="Dependencies" state={readiness} />
        </div>
      </section>
    </main>
  )
}

export default App
