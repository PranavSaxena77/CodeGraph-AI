import { useEffect, useRef, useState } from 'react'

import { Spinner } from './Ui.jsx'
import { PROCESSING_ACTIVITY } from './processingActivity.js'

const ACTIVITY_STEP_MS = 650

function formatElapsed(milliseconds) {
  const totalSeconds = Math.floor(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function ProcessingActivity({ stage, state = 'running', compact = false }) {
  const activity = PROCESSING_ACTIVITY[stage]
  const [elapsed, setElapsed] = useState(0)
  const [activeIndex, setActiveIndex] = useState(0)
  const activeEntryRef = useRef(null)

  useEffect(() => {
    if (state !== 'running') return undefined
    const startedAt = performance.now()
    setElapsed(0)
    setActiveIndex(0)
    const interval = window.setInterval(() => {
      const nextElapsed = performance.now() - startedAt
      setElapsed(nextElapsed)
      setActiveIndex(Math.min(Math.floor(nextElapsed / ACTIVITY_STEP_MS), activity.entries.length - 1))
    }, 250)
    return () => window.clearInterval(interval)
  }, [activity.entries.length, stage, state])

  useEffect(() => {
    activeEntryRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [activeIndex])

  const isComplete = state === 'complete'
  const accessibleState = state === 'running' ? { role: 'status', 'aria-live': 'polite' } : {}

  return (
    <section className={`processing-activity ${compact ? 'processing-activity--compact' : ''}`} aria-label={`Processing Activity — ${activity.label}`} {...accessibleState}>
      <header className="processing-activity__header">
        <div><span>PROCESSING ACTIVITY</span><strong>{activity.label}</strong></div>
        <span className={`processing-activity__state processing-activity__state--${state}`}>{state === 'running' && <Spinner />}<code>{isComplete ? 'COMPLETE' : state === 'failed' ? 'FAILED' : `UI ELAPSED ${formatElapsed(elapsed)}`}</code></span>
      </header>
      <ol className="processing-activity__entries">
        {activity.entries.map((entry, index) => {
          const entryState = isComplete || index < activeIndex ? 'complete' : state === 'failed' && index === activeIndex ? 'failed' : index === activeIndex && state === 'running' ? 'active' : 'pending'
          const marker = entryState === 'complete' ? 'DONE' : entryState === 'active' ? formatElapsed(elapsed) : entryState === 'failed' ? 'FAIL' : '—'
          return (
            <li className={`processing-activity__entry processing-activity__entry--${entryState}`} key={entry} ref={entryState === 'active' ? activeEntryRef : undefined}>
              <code>{marker}</code><span aria-hidden="true" /><strong>{entry}</strong>
            </li>
          )
        })}
      </ol>
      {!compact && <footer>Client-side operation sequence · Not a stream of backend log events</footer>}
    </section>
  )
}

export function RepositoryActivity({ operation, stages, compact = false }) {
  const entriesRef = useRef(null)
  const followLatestRef = useRef(true)
  const events = operation.data?.events ?? []
  const currentStage = ['ingestion', 'analysis', 'graph', 'vector'].find((stage) => stages[stage] === 'running' || stages[stage] === 'failed')
  const isRunning = Boolean(currentStage && stages[currentStage] === 'running')

  useEffect(() => {
    if (!followLatestRef.current || !entriesRef.current) return
    entriesRef.current.scrollTop = entriesRef.current.scrollHeight
  }, [events.length])

  function handleScroll(event) {
    const element = event.currentTarget
    followLatestRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 32
  }

  return (
    <section className={`repository-activity ${compact ? 'repository-activity--compact' : ''}`} aria-label="Live Backend Activity" aria-live={isRunning ? 'polite' : undefined} role={isRunning ? 'status' : undefined}>
      <header><div><span className="panel__kicker">Backend operation events</span><h2>Live Backend Activity</h2></div><span className={`live-indicator ${isRunning ? 'live-indicator--active' : ''}`}><i />{isRunning ? 'Live' : operation.data?.status === 'complete' ? 'Complete' : operation.data?.status === 'failed' ? 'Failed' : 'Idle'}</span></header>
      <ol className="repository-activity__entries" onScroll={handleScroll} ref={entriesRef}>
        {events.map((event) => <li className={`repository-activity__entry repository-activity__entry--${event.status}`} key={event.id}><time dateTime={event.completed_at ?? event.started_at}>{formatBackendTime(event.completed_at ?? event.started_at)}</time><i className="activity-status-dot" aria-hidden="true" /><code className="activity-status">{event.status.toUpperCase()}</code><strong>{event.message}</strong>{event.metric && <span className="repository-activity__metric"><b>{event.metric.value.toLocaleString()}</b>{event.metric.label}</span>}</li>)}
        {events.length === 0 && <li className="repository-activity__empty">{isRunning ? <><Spinner /> Waiting for the backend to report the first operation…</> : 'Run the pipeline to begin structural and semantic processing.'}</li>}
      </ol>
      <footer><span>Source: <strong>FastAPI operation registry</strong></span><span>Events: <code>{events.length}</code></span>{operation.error && <small>{operation.error}</small>}</footer>
    </section>
  )
}

function formatBackendTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
