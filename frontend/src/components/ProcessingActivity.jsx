import { useEffect, useRef, useState } from 'react'

import { Spinner } from './Ui.jsx'
import { PIPELINE_ACTIVITY_STAGES, PROCESSING_ACTIVITY } from './processingActivity.js'

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

export function RepositoryActivity({ stages }) {
  const currentStage = PIPELINE_ACTIVITY_STAGES.find((stage) => stages[stage] === 'running' || stages[stage] === 'failed')
  const visibleStages = PIPELINE_ACTIVITY_STAGES.filter((stage) => stages[stage] === 'complete' || stage === currentStage)
  const activeActivity = currentStage ? PROCESSING_ACTIVITY[currentStage] : null
  const [elapsed, setElapsed] = useState(0)
  const [activeIndex, setActiveIndex] = useState(0)
  const activeEntryRef = useRef(null)

  useEffect(() => {
    if (!currentStage || stages[currentStage] !== 'running') return undefined
    const startedAt = performance.now()
    setElapsed(0)
    setActiveIndex(0)
    const interval = window.setInterval(() => {
      const nextElapsed = performance.now() - startedAt
      setElapsed(nextElapsed)
      setActiveIndex(Math.min(Math.floor(nextElapsed / ACTIVITY_STEP_MS), activeActivity.entries.length - 1))
    }, 250)
    return () => window.clearInterval(interval)
  }, [activeActivity, currentStage, stages])

  useEffect(() => { activeEntryRef.current?.scrollIntoView?.({ block: 'nearest' }) }, [activeIndex])

  const stageLabel = currentStage ? PROCESSING_ACTIVITY[currentStage].label : stages.vector === 'complete' ? 'Pipeline complete' : 'Repository ingestion'
  return (
    <section className="repository-activity" aria-label="Processing Activity" aria-live={currentStage ? 'polite' : undefined} role={currentStage ? 'status' : undefined}>
      <header><div><span className="panel__kicker">CLIENT OPERATION SEQUENCE</span><h2>Processing Activity</h2></div><span className={`live-indicator ${currentStage ? 'live-indicator--active' : ''}`}><i />{currentStage ? 'Live' : 'Idle'}</span></header>
      <ol className="repository-activity__entries">
        {visibleStages.flatMap((stage) => PROCESSING_ACTIVITY[stage].entries.map((entry, index) => {
          const stageState = stages[stage]
          const entryState = stageState === 'complete' || (stageState === 'running' && index < activeIndex) ? 'complete' : stageState === 'failed' && index === activeIndex ? 'failed' : stageState === 'running' && index === activeIndex ? 'active' : 'pending'
          const marker = entryState === 'complete' ? 'DONE' : entryState === 'active' ? formatElapsed(elapsed) : entryState === 'failed' ? 'FAIL' : '—'
          return <li className={`repository-activity__entry repository-activity__entry--${entryState}`} key={`${stage}-${entry}`} ref={entryState === 'active' ? activeEntryRef : undefined}><code>{marker}</code><span /><strong>{entry}</strong></li>
        }))}
        {visibleStages.length === 0 && <li className="repository-activity__empty">Run the pipeline to begin structural and semantic processing.</li>}
      </ol>
      <footer><span>Stage: <strong>{stageLabel}</strong></span><span>Elapsed: <code>{currentStage ? formatElapsed(elapsed) : '—'}</code></span><small>Processing Activity is client-side and not backend logs.</small></footer>
    </section>
  )
}

export function PipelineActivity({ stages }) {
  const completedStages = PIPELINE_ACTIVITY_STAGES.filter((stage) => stages[stage] === 'complete')
  const currentStage = PIPELINE_ACTIVITY_STAGES.find((stage) => stages[stage] === 'running' || stages[stage] === 'failed')

  if (completedStages.length === 0 && !currentStage) return null

  return (
    <div className="pipeline-activity">
      {completedStages.map((stage) => (
        <details className="activity-history" key={stage}>
          <summary><span>{PROCESSING_ACTIVITY[stage].label}</span><code>{PROCESSING_ACTIVITY[stage].entries.length} ACTIVITIES COMPLETE</code></summary>
          <ProcessingActivity stage={stage} state="complete" compact />
        </details>
      ))}
      {currentStage && <ProcessingActivity stage={currentStage} state={stages[currentStage]} />}
    </div>
  )
}
