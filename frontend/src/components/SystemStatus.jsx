function ServiceRow({ name, description, state }) {
  const label = state === 'available' ? 'Available' : state === 'loading' ? 'Checking' : 'Unavailable'
  return (
    <div className="service-row" data-state={state}>
      <span className={`signal signal--${state}`} aria-hidden="true" />
      <div><strong>{name}</strong><p>{description}</p></div>
      <code className="service-row__state">{state === 'available' ? 'CONNECTION_OK' : state === 'loading' ? 'CHECK_PENDING' : 'CONNECTION_FAILED'}</code>
      <span className={`status-badge status-badge--${state === 'available' ? 'complete' : state}`}>{label}</span>
    </div>
  )
}

export default function SystemStatus({ health, readiness }) {
  const dependencyState = (name) => {
    if (readiness.loading) return 'loading'
    return readiness.data?.dependencies?.[name]?.status === 'ready' ? 'available' : 'unavailable'
  }
  const backendState = health.loading ? 'loading' : health.data ? 'available' : 'unavailable'

  return (
    <section className="view" aria-labelledby="system-title">
      <div className="view-heading"><div><p className="eyebrow">Operations</p><h1 id="system-title">System status</h1></div><p>Live readiness checks for required application services.</p></div>
      <div className="panel system-panel">
        <div className="panel__heading"><div><span className="panel__kicker">INFRASTRUCTURE</span><h2>Service availability</h2><p>Readiness is reported directly by the FastAPI backend.</p></div><span className="last-check">LIVE CHECK · CURRENT SESSION</span></div>
        <div className="service-list">
          <ServiceRow name="Backend" description={health.data ? `${health.data.application} v${health.data.version}` : health.error ?? 'Checking API liveness.'} state={backendState} />
          <ServiceRow name="MongoDB" description="Repository and snapshot metadata" state={dependencyState('mongodb')} />
          <ServiceRow name="Neo4j" description="Structural code graph" state={dependencyState('neo4j')} />
        </div>
      </div>
    </section>
  )
}
