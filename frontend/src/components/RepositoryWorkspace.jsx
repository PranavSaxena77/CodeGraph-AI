import { useState } from 'react'

import { RepositoryActivity } from './ProcessingActivity.jsx'
import { GraphPreview, MetricsPreview } from './RepositoryVisuals.jsx'
import { ErrorPanel, Icon, Spinner } from './Ui.jsx'

const GITHUB_REPOSITORY_PATTERN = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/
const stageLabels = {
  ingestion: { label: 'Repository ingestion', detail: 'Fetch and snapshot repository' },
  analysis: { label: 'Structural analysis', detail: 'Analyze Python code structure' },
  graph: { label: 'Code graph', detail: 'Persist structural relationships' },
  vector: { label: 'Semantic index', detail: 'Build vector index' },
}

export function RepositoryForm({ loading, onSubmit }) {
  const [githubUrl, setGithubUrl] = useState('')
  const [validationError, setValidationError] = useState('')
  function submit(event) {
    event.preventDefault()
    const value = githubUrl.trim()
    if (!GITHUB_REPOSITORY_PATTERN.test(value)) { setValidationError('Enter a complete public GitHub repository URL.'); return }
    setValidationError(''); onSubmit(value)
  }
  return <form className="repository-form" onSubmit={submit} noValidate><label htmlFor="repository-url">GitHub repository URL</label><div className="input-row"><input id="repository-url" value={githubUrl} onChange={(event) => setGithubUrl(event.target.value)} placeholder="https://github.com/owner/repository" autoComplete="url" aria-describedby={validationError ? 'repository-url-error' : 'repository-url-help'} aria-invalid={Boolean(validationError)} disabled={loading} /><button className="button button--primary" disabled={loading} type="submit">{loading && <Spinner />}<span>{loading ? 'Connecting source' : 'Register repository'}</span></button></div>{validationError ? <p className="field-error" id="repository-url-error" role="alert">{validationError}</p> : <p className="field-help" id="repository-url-help">Public GitHub repositories only. Analysis is pinned to an immutable commit.</p>}</form>
}

function CopyControl({ value, label }) {
  const [copied, setCopied] = useState(false)
  async function copy() { if (!navigator.clipboard?.writeText) return; await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1600) }
  return <button aria-label={copied ? `${label} copied` : `Copy ${label}`} className="copy-control" onClick={copy} title={`Copy ${label}`} type="button"><Icon name="copy" size={13} /><span>{copied ? 'Copied' : 'Copy'}</span></button>
}

export function PipelineStatus({ stages, operation, variant = 'vertical' }) {
  return <ol className={`pipeline pipeline--${variant}`} aria-label="Repository processing pipeline" data-orientation={variant}>{Object.entries(stageLabels).map(([key, stage], index) => { const state = stages[key]; const duration = getStageDuration(operation?.data?.events ?? [], key, state); return <li className={`pipeline__stage pipeline__stage--${state}`} key={key}><span className="pipeline__track" aria-hidden="true"><i className="pipeline__connector pipeline__connector--before" /><span className="pipeline__index">{state === 'complete' ? <Icon name="check" size={16} /> : state === 'running' ? <Spinner /> : state === 'failed' ? '!' : index + 1}</span><i className="pipeline__connector pipeline__connector--after" /></span><span className="pipeline__copy"><strong>{stage.label}</strong><span>{stage.detail}</span><small><b>{state === 'running' ? 'Running' : state[0].toUpperCase() + state.slice(1)}</b>{duration && <time>{duration}</time>}</small></span></li> })}</ol>
}

function getStageDuration(events, stage, state) {
  if (state !== 'complete') return ''
  const completed = events.filter((event) => event.stage === stage && event.completed_at)
  if (completed.length === 0) return ''
  const startedAt = Math.min(...completed.map((event) => Date.parse(event.started_at)))
  const completedAt = Math.max(...completed.map((event) => Date.parse(event.completed_at)))
  if (!Number.isFinite(startedAt) || !Number.isFinite(completedAt) || completedAt < startedAt) return ''
  const seconds = (completedAt - startedAt) / 1000
  return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`
}

function RepositoryHeader({ repository, snapshot, indexReady }) {
  const metadata = [
    { label: 'Branch', value: snapshot.ref },
    { label: 'Commit', value: snapshot.commit_sha.slice(0, 7), copy: <CopyControl value={snapshot.commit_sha} label="commit SHA" /> },
    { label: 'Snapshot', value: snapshot.id, copy: <CopyControl value={snapshot.id} label="snapshot ID" /> },
    { label: 'Python files', value: snapshot.discovered_file_count },
  ]
  return <header className="repository-header"><div className="repository-header__identity"><span className="repository-title__mark"><Icon name="repository" size={26} /></span><div className="repository-title"><h1 id="repository-title"><span>{repository.owner}</span><b>/</b>{repository.name}</h1><span className="visibility-badge">Public</span></div></div><div className="repository-header__details"><dl className="repository-meta">{metadata.map((item) => <div key={item.label}><dt>{item.label}</dt><dd><code title={String(item.value)}>{item.value}</code>{item.copy}</dd></div>)}<div><dt>Indexed</dt><dd className={indexReady ? 'meta-ready' : ''}>{indexReady ? 'Yes' : 'Pending'}</dd></div><div><dt>Updated</dt><dd><time dateTime={snapshot.created_at}>{new Date(snapshot.created_at).toLocaleString()}</time></dd></div></dl></div></header>
}

function Artifacts({ stages }) {
  const artifacts = [{ stage: 'analysis', icon: 'code', title: 'Structural Analysis', description: 'Python AST, symbols, imports, calls' }, { stage: 'graph', icon: 'graph', title: 'Code Graph', description: 'Repository-scoped relationships' }, { stage: 'vector', icon: 'layers', title: 'Semantic Index', description: 'Vector index over source chunks' }]
  return <section className="panel artifacts" aria-labelledby="artifacts-title"><div className="compact-panel-heading"><h2 id="artifacts-title">Artifacts</h2><span>Snapshot scoped</span></div><div className="artifact-grid">{artifacts.map((artifact) => <article className="artifact-card" key={artifact.stage}><span className={`artifact-card__icon artifact-card__icon--${stages[artifact.stage]}`}><Icon name={artifact.icon} /></span><div><h3>{artifact.title}</h3><p>{artifact.description}</p></div><span className={`status-badge status-badge--${stages[artifact.stage]}`}>{stages[artifact.stage] === 'running' ? 'Running' : stages[artifact.stage][0].toUpperCase() + stages[artifact.stage].slice(1)}</span></article>)}</div></section>
}

function SnapshotPanel({ repository, snapshot }) {
  return <section className="panel snapshot-panel"><div className="compact-panel-heading"><div><h2>Immutable snapshot</h2><p>The registered source revision used by every repository artifact.</p></div></div><dl className="snapshot-grid"><div><dt>Repository ID</dt><dd>{repository.id}</dd></div><div><dt>Snapshot ID</dt><dd>{snapshot.id}</dd></div><div><dt>Commit SHA</dt><dd>{snapshot.commit_sha}</dd></div><div><dt>Status</dt><dd>{snapshot.status.replaceAll('_', ' ')}</dd></div></dl></section>
}

export default function RepositoryWorkspace({ repository, snapshot, stages, operation, graphPreview, registrationState, analysisState, analysisSummary, onRegister, onAnalyze, onOpenIntelligence }) {
  const [activeTab, setActiveTab] = useState('overview')
  if (!repository) return <section className="view repository-view repository-view--onboarding" aria-labelledby="repository-title"><div className="view-heading"><div><p className="eyebrow">Workspace</p><h1 id="repository-title">Repository Intelligence</h1></div><p>Build structural and semantic representations of a public Python repository.</p></div><div className="onboarding-workspace"><div className="panel panel--form"><div className="panel__heading"><div><span className="panel__kicker">Source connection</span><h2>Connect repository</h2><p>Source is fetched read-only and pinned to an immutable commit.</p></div></div><RepositoryForm loading={registrationState.loading} onSubmit={onRegister} />{registrationState.loading && <RepositoryActivity compact operation={operation} stages={stages} />}{registrationState.error && <ErrorPanel compact title="Repository unavailable" message={registrationState.error} />}</div><aside className="onboarding-details" aria-label="Analysis outputs"><div className="onboarding-details__heading"><span className="panel__kicker">Index outputs</span><strong>Repository model</strong></div>{['Structural analysis|Python files, symbols, imports, calls', 'Code graph|Repository-scoped relationships', 'Semantic index|Evidence-ready source chunks'].map((item, index) => { const [title, detail] = item.split('|'); return <div className="output-row" key={title}><span>0{index + 1}</span><div><strong>{title}</strong><small>{detail}</small></div></div> })}</aside></div></section>

  const indexReady = stages.ready === 'complete'
  return <section className="repository-view repository-view--active" aria-labelledby="repository-title"><RepositoryHeader repository={repository} snapshot={snapshot} indexReady={indexReady} /><div className="repository-tabs" role="tablist" aria-label="Repository workspace"><button aria-selected={activeTab === 'overview'} id="overview-tab" onClick={() => setActiveTab('overview')} role="tab" type="button"><Icon name="repository" size={16} />Overview</button><button aria-selected={activeTab === 'snapshots'} id="snapshots-tab" onClick={() => setActiveTab('snapshots')} role="tab" type="button"><Icon name="clock" size={16} />Snapshots</button></div>{activeTab === 'snapshots' ? <div role="tabpanel" aria-labelledby="snapshots-tab"><SnapshotPanel repository={repository} snapshot={snapshot} /></div> : <div className="repository-dashboard" role="tabpanel" aria-labelledby="overview-tab"><main className="repository-dashboard__main"><section className="panel pipeline-operation-panel"><div className="pipeline-progress-panel"><div className="compact-panel-heading"><div><h2>Pipeline Progress</h2><p>Backend-confirmed stage state</p></div><span>4 stages</span></div><PipelineStatus stages={stages} operation={operation} variant="horizontal" /></div><RepositoryActivity operation={operation} stages={stages} /></section><div className="repository-previews"><MetricsPreview metrics={analysisSummary} stages={stages} /><GraphPreview preview={graphPreview} graphState={stages.graph} /></div>{analysisState.error && <ErrorPanel title={`${analysisState.failedStage} failed`} message={analysisState.error} actionLabel="Retry pipeline" onAction={onAnalyze} />}</main><aside className="repository-rail"><section className="panel rail-panel"><div className="compact-panel-heading"><h2>Pipeline</h2><span>4 stages</span></div><PipelineStatus stages={stages} operation={operation} /></section><Artifacts stages={stages} /><section className="panel actions-panel"><div className="compact-panel-heading"><h2>Actions</h2></div><div><button className="button button--primary" type="button" onClick={onOpenIntelligence} disabled={!indexReady}>View Intelligence</button><button className="button button--secondary" type="button" onClick={onAnalyze} disabled={analysisState.loading || indexReady}>{analysisState.loading && <Spinner />}{analysisState.loading ? 'Processing snapshot' : indexReady ? 'Pipeline complete' : 'Run pipeline'}</button></div></section></aside></div>}</section>
}
