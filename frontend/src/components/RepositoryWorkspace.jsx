import { useState } from 'react'

import { ProcessingActivity, RepositoryActivity } from './ProcessingActivity.jsx'
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
  return <button aria-label={copied ? `${label} copied` : `Copy ${label}`} className="copy-control" onClick={copy} type="button"><Icon name="copy" size={13} /><span>{copied ? 'Copied' : 'Copy'}</span></button>
}

export function PipelineStatus({ stages }) {
  return <ol className="pipeline" aria-label="Repository processing pipeline">{Object.entries(stageLabels).map(([key, stage], index) => { const state = stages[key]; return <li className={`pipeline__stage pipeline__stage--${state}`} key={key}><span className="pipeline__index">{state === 'complete' ? '✓' : state === 'running' ? <Spinner label={`${stage.label} running`} /> : index + 1}</span><span className="pipeline__copy"><strong>{stage.label}</strong><span>{stage.detail}</span><small>{state === 'running' ? 'IN PROGRESS' : state.toUpperCase()}</small></span></li> })}</ol>
}

function RepositoryHeader({ repository, snapshot, indexReady }) {
  return <header className="repository-header"><div className="breadcrumb"><span>Repositories</span><b>/</b><code>{repository.owner}/{repository.name}</code></div><div className="repository-header__main"><div><div className="repository-title"><Icon name="repository" size={21} /><h1>{repository.owner} / {repository.name}</h1><span className="visibility-badge">Public</span></div><div className="repository-meta"><span>Branch <code>{snapshot.ref}</code></span><span>Commit <code>{snapshot.commit_sha.slice(0, 7)}</code><CopyControl value={snapshot.commit_sha} label="commit SHA" /></span><span>Snapshot <code>{snapshot.id}</code></span><span>Python files <code>{snapshot.discovered_file_count}</code></span><span className={indexReady ? 'meta-ready' : ''}>{indexReady ? 'Indexed' : 'Index pending'}</span></div></div><div className="repository-header__actions"><span>Updated <code>{new Date(snapshot.created_at).toLocaleDateString()}</code></span><a className="button button--secondary" href={repository.github_url} target="_blank" rel="noreferrer">View on GitHub <Icon name="external" size={14} /></a></div></div></header>
}

function RepositoryDetails({ repository, snapshot, analysisSummary }) {
  const rows = [['Owner', repository.owner], ['Repository', repository.name], ['Visibility', 'Public'], ['Default Branch', repository.default_branch], ['Snapshot ID', snapshot.id], ['Commit SHA', snapshot.commit_sha], ['Language (primary)', 'Python'], ['Total Python Files', snapshot.discovered_file_count], ['Analyzed At', analysisSummary?.completedAt ? new Date(analysisSummary.completedAt).toLocaleString() : 'Not analyzed']]
  return <section className="panel details-panel" aria-labelledby="details-title"><div className="compact-panel-heading"><h2 id="details-title">Repository Details</h2></div><dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="mono">{value}</dd></div>)}</dl></section>
}

function Artifacts({ stages }) {
  const artifacts = [{ stage: 'analysis', icon: 'code', title: 'Structural Analysis', description: 'Python AST, symbols, imports, calls' }, { stage: 'graph', icon: 'graph', title: 'Code Graph', description: 'Repository-scoped relationships' }, { stage: 'vector', icon: 'layers', title: 'Semantic Index', description: 'Vector index over source chunks' }]
  return <section className="artifacts" aria-labelledby="artifacts-title"><div className="section-heading"><h2 id="artifacts-title">Artifacts</h2><span>Snapshot-scoped outputs</span></div><div className="artifact-grid">{artifacts.map((artifact) => <article className="artifact-card" key={artifact.stage}><span className={`artifact-card__icon artifact-card__icon--${stages[artifact.stage]}`}><Icon name={artifact.icon} /></span><div><h3>{artifact.title}</h3><p>{artifact.description}</p></div><span className={`status-badge status-badge--${stages[artifact.stage]}`}>{stages[artifact.stage] === 'running' ? 'IN PROGRESS' : stages[artifact.stage].toUpperCase()}</span></article>)}</div></section>
}

function SnapshotPanel({ repository, snapshot }) {
  return <section className="panel snapshot-panel"><div className="compact-panel-heading"><div><h2>Immutable snapshot</h2><p>The registered source revision used by every repository artifact.</p></div></div><dl className="snapshot-grid"><div><dt>Repository ID</dt><dd>{repository.id}</dd></div><div><dt>Snapshot ID</dt><dd>{snapshot.id}</dd></div><div><dt>Commit SHA</dt><dd>{snapshot.commit_sha}</dd></div><div><dt>Status</dt><dd>{snapshot.status.replaceAll('_', ' ')}</dd></div></dl></section>
}

export default function RepositoryWorkspace({ repository, snapshot, stages, registrationState, analysisState, analysisSummary, onRegister, onAnalyze, onOpenIntelligence }) {
  const [activeTab, setActiveTab] = useState('overview')
  if (!repository) return <section className="view repository-view repository-view--onboarding" aria-labelledby="repository-title"><div className="view-heading"><div><p className="eyebrow">Workspace</p><h1 id="repository-title">Repository Intelligence</h1></div><p>Build structural and semantic representations of a public Python repository.</p></div><div className="onboarding-workspace"><div className="panel panel--form"><div className="panel__heading"><div><span className="panel__kicker">SOURCE CONNECTION</span><h2>Connect repository</h2><p>Source is fetched read-only and pinned to an immutable commit.</p></div></div><RepositoryForm loading={registrationState.loading} onSubmit={onRegister} />{registrationState.loading && <ProcessingActivity stage="ingestion" />}{registrationState.error && <ErrorPanel compact title="Repository unavailable" message={registrationState.error} />}</div><aside className="onboarding-details" aria-label="Analysis outputs"><div className="onboarding-details__heading"><span className="panel__kicker">INDEX OUTPUTS</span><strong>Repository model</strong></div>{['Structural analysis|Python files, symbols, imports, calls', 'Code graph|Repository-scoped relationships', 'Semantic index|Evidence-ready source chunks'].map((item, index) => { const [title, detail] = item.split('|'); return <div className="output-row" key={title}><span>0{index + 1}</span><div><strong>{title}</strong><small>{detail}</small></div></div> })}</aside></div></section>

  return <section className="repository-view repository-view--active" aria-labelledby="repository-title"><RepositoryHeader repository={repository} snapshot={snapshot} indexReady={stages.ready === 'complete'} /><div className="repository-tabs" role="tablist" aria-label="Repository workspace"><button aria-selected={activeTab === 'overview'} id="overview-tab" onClick={() => setActiveTab('overview')} role="tab" type="button">Overview</button><button aria-selected={activeTab === 'snapshots'} id="snapshots-tab" onClick={() => setActiveTab('snapshots')} role="tab" type="button">Snapshots</button></div>{activeTab === 'snapshots' ? <div role="tabpanel" aria-labelledby="snapshots-tab"><SnapshotPanel repository={repository} snapshot={snapshot} /></div> : <div className="repository-layout" role="tabpanel" aria-labelledby="overview-tab"><div className="repository-content"><div className="repository-primary-grid"><RepositoryActivity stages={stages} /><RepositoryDetails repository={repository} snapshot={snapshot} analysisSummary={analysisSummary} /></div>{analysisState.error && <ErrorPanel title={`${analysisState.failedStage} failed`} message={analysisState.error} actionLabel="Retry pipeline" onAction={onAnalyze} />}<Artifacts stages={stages} /></div><aside className="repository-rail"><section className="panel rail-panel"><div className="compact-panel-heading"><h2>Pipeline</h2><span>4 stages</span></div><PipelineStatus stages={stages} /></section><section className="panel actions-panel"><div className="compact-panel-heading"><h2>Actions</h2></div><div><button className="button button--primary" type="button" onClick={onAnalyze} disabled={analysisState.loading || stages.ready === 'complete'}>{analysisState.loading && <Spinner />}{analysisState.loading ? 'Processing snapshot' : stages.ready === 'complete' ? 'Pipeline complete' : 'Run pipeline'}</button><button className="button button--secondary" type="button" onClick={onOpenIntelligence} disabled={stages.ready !== 'complete'}>Open Intelligence</button></div></section></aside></div>}</section>
}
