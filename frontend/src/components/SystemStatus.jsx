import { ErrorPanel, Spinner, StatusIndicator } from './Ui.jsx'

function ServiceRow({ name, description, state, lastChecked }) {
  const label = state === 'available' ? 'Available' : state === 'degraded' ? 'Degraded' : state === 'loading' ? 'Checking' : 'Unavailable'
  return (
    <tr data-state={state}>
      <th scope="row"><span className={`signal signal--${state} ${state === 'loading' ? 'signal--pulse' : ''}`} aria-hidden="true" /><strong>{name}</strong></th>
      <td><span className={`status-badge status-badge--${state === 'available' ? 'complete' : state}`}>{label}</span></td>
      <td>{description}</td>
      <td><code>{lastChecked}</code></td>
    </tr>
  )
}

export default function SystemStatus({ health, readiness, lastRefresh, onRefresh }) {
  const dependencyState = (name) => {
    if (readiness.loading) return 'loading'
    const status = readiness.data?.dependencies?.[name]?.status
    if (status === 'ready') return 'available'
    if (status && status !== 'unavailable') return 'degraded'
    return 'unavailable'
  }
  const backendState = health.loading ? 'loading' : health.data ? 'available' : 'unavailable'
  const refreshing = health.loading || readiness.loading
  const overallState = refreshing ? 'loading' : backendState === 'available' && dependencyState('mongodb') === 'available' && dependencyState('neo4j') === 'available' ? 'available' : backendState === 'unavailable' ? 'unavailable' : 'degraded'
  const overallLabel = { loading: 'Refreshing service state', available: 'All systems operational', degraded: 'Partial service degradation', unavailable: 'Backend unavailable' }[overallState]
  const refreshedLabel = lastRefresh ? lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Not yet checked'

  return (
    <section className="view" aria-labelledby="system-title">
      <div className="view-heading"><div><p className="eyebrow">Operations</p><h1 id="system-title">System status</h1></div><p>Live readiness checks for required application services.</p></div>
      <div className="panel system-panel">
        <div className="panel__heading panel__heading--action"><div><span className="panel__kicker">Infrastructure</span><h2>Service availability</h2><p>Readiness reported directly by the FastAPI backend.</p></div><button className="button button--secondary" type="button" onClick={onRefresh} disabled={refreshing}>{refreshing && <Spinner />}<span>{refreshing ? 'Refreshing' : 'Refresh status'}</span></button></div>
        <div className="system-summary"><StatusIndicator state={overallState} label={overallLabel} pulse={refreshing} /><span>Last refreshed <code>{refreshedLabel}</code></span></div>
        <div className="service-table-wrap"><table className="service-table"><thead><tr><th>Service</th><th>Status</th><th>Details</th><th>Last checked</th></tr></thead><tbody>
          <ServiceRow name="Backend" description={health.data ? `${health.data.application} v${health.data.version}` : health.error ?? 'Checking API liveness.'} state={backendState} lastChecked={refreshedLabel} />
          <ServiceRow name="MongoDB" description="Repository and snapshot metadata" state={dependencyState('mongodb')} lastChecked={refreshedLabel} />
          <ServiceRow name="Neo4j" description="Structural code graph" state={dependencyState('neo4j')} lastChecked={refreshedLabel} />
        </tbody></table></div>
        {(health.error || readiness.error) && <ErrorPanel compact title="Status refresh incomplete" message={health.error || readiness.error} actionLabel="Retry refresh" onAction={onRefresh} />}
      </div>
    </section>
  )
}
