import { useState } from 'react'

const GITHUB_REPOSITORY_PATTERN = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/
const stageLabels = { ingestion: 'Ingestion', analysis: 'Analysis', graph: 'Graph Index', vector: 'Vector Index', ready: 'Ready' }

export function RepositoryForm({ loading, onSubmit }) {
  const [githubUrl, setGithubUrl] = useState('')
  const [validationError, setValidationError] = useState('')

  function submit(event) {
    event.preventDefault()
    const value = githubUrl.trim()
    if (!GITHUB_REPOSITORY_PATTERN.test(value)) {
      setValidationError('Enter a complete public GitHub repository URL.')
      return
    }
    setValidationError('')
    onSubmit(value)
  }

  return (
    <form className="repository-form" onSubmit={submit} noValidate>
      <label htmlFor="repository-url">GitHub repository URL</label>
      <div className="input-row">
        <input id="repository-url" value={githubUrl} onChange={(event) => setGithubUrl(event.target.value)} placeholder="https://github.com/owner/repository" autoComplete="url" aria-describedby={validationError ? 'repository-url-error' : 'repository-url-help'} aria-invalid={Boolean(validationError)} disabled={loading} />
        <button className="button button--primary" disabled={loading} type="submit">{loading ? 'Registering…' : 'Register repository'}</button>
      </div>
      {validationError ? <p className="field-error" id="repository-url-error" role="alert">{validationError}</p> : <p className="field-help" id="repository-url-help">Public GitHub repositories only. Analysis is pinned to an immutable commit.</p>}
    </form>
  )
}

export function PipelineStatus({ stages }) {
  return (
    <ol className="pipeline" aria-label="Repository processing pipeline">
      {Object.entries(stageLabels).map(([key, label], index) => {
        const state = stages[key]
        return (
          <li className={`pipeline__stage pipeline__stage--${state}`} key={key}>
            <span className="pipeline__index">{String(index + 1).padStart(2, '0')}</span>
            <span className="pipeline__copy"><strong>{label}</strong><small>{state.toUpperCase()}</small></span>
          </li>
        )
      })}
    </ol>
  )
}

function MetadataItem({ label, value, mono = false }) {
  return <div className="metadata-item"><dt>{label}</dt><dd className={mono ? 'mono' : ''}>{value}</dd></div>
}

export default function RepositoryWorkspace({ repository, snapshot, stages, registrationState, analysisState, analysisSummary, onRegister, onAnalyze }) {
  return (
    <section className={`view repository-view ${repository ? 'repository-view--active' : 'repository-view--onboarding'}`} aria-labelledby="repository-title">
      <div className="view-heading">
        <div><p className="eyebrow">Workspace</p><h1 id="repository-title">{repository ? 'Repository dashboard' : 'Repository Intelligence'}</h1></div>
        <p>{repository ? 'Inspect the immutable source context and build snapshot-scoped structural and semantic indexes.' : 'Build structural and semantic representations of a public Python repository.'}</p>
      </div>

      {!repository ? (
        <div className="onboarding-workspace">
          <div className="panel panel--form">
            <div className="panel__heading"><div><span className="panel__kicker">SOURCE CONNECTION</span><h2>Connect repository</h2><p>Source is fetched read-only and pinned to an immutable commit.</p></div></div>
            <RepositoryForm loading={registrationState.loading} onSubmit={onRegister} />
            {registrationState.error && <div className="notice notice--error" role="alert"><strong>Repository unavailable</strong><span>{registrationState.error}</span></div>}
          </div>
          <aside className="onboarding-details" aria-label="Analysis outputs">
            <div className="onboarding-details__heading"><span className="panel__kicker">INDEX OUTPUTS</span><strong>Repository model</strong></div>
            <div className="output-row"><span>01</span><div><strong>Structural analysis</strong><small>Python files, symbols, imports, calls</small></div></div>
            <div className="output-row"><span>02</span><div><strong>Code graph</strong><small>Repository-scoped relationships</small></div></div>
            <div className="output-row"><span>03</span><div><strong>Semantic index</strong><small>Evidence-ready source chunks</small></div></div>
          </aside>
        </div>
      ) : (
        <div className="repository-dashboard">
          <section className="panel overview-panel" aria-labelledby="overview-title">
            <div className="panel__heading panel__heading--action">
              <div><span className="panel__kicker">ACTIVE SNAPSHOT</span><h2 id="overview-title">Repository overview</h2><p>Immutable source context for the active workspace.</p></div>
              <button className="button button--primary" type="button" onClick={onAnalyze} disabled={analysisState.loading || stages.ready === 'complete'}>{analysisState.loading ? 'Processing…' : stages.ready === 'complete' ? 'Analysis complete' : 'Run analysis'}</button>
            </div>
            <dl className="metadata-grid">
              <MetadataItem label="Repository" value={`${repository.owner}/${repository.name}`} mono />
              <MetadataItem label="Default branch" value={repository.default_branch} mono />
              <MetadataItem label="Commit SHA" value={snapshot.commit_sha} mono />
              <MetadataItem label="Snapshot ID" value={snapshot.id} mono />
              <MetadataItem label="Python files" value={snapshot.discovered_file_count} />
              <MetadataItem label="Snapshot status" value={snapshot.status.replaceAll('_', ' ').toUpperCase()} />
            </dl>
          </section>

          <section className="panel pipeline-panel" aria-labelledby="pipeline-title">
            <div className="panel__heading"><div><span className="panel__kicker">INDEX PIPELINE</span><h2 id="pipeline-title">Processing pipeline</h2><p>Each stage writes deterministic output scoped to this snapshot.</p></div><code className="snapshot-context">{snapshot.id}</code></div>
            <PipelineStatus stages={stages} />
            {analysisState.error && <div className="notice notice--error" role="alert"><strong>{analysisState.failedStage} failed</strong><span>{analysisState.error}</span></div>}
            {analysisSummary && <div className="pipeline-summary" aria-label="Analysis summary"><span><strong>{analysisSummary.symbols}</strong> symbols</span><span><strong>{analysisSummary.nodes}</strong> graph nodes</span><span><strong>{analysisSummary.relationships}</strong> relationships</span><span><strong>{analysisSummary.chunks}</strong> vector chunks</span></div>}
          </section>
        </div>
      )}
    </section>
  )
}
