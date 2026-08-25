import { useState } from 'react'

function SourceSnippet({ content, startLine }) {
  const lines = content.split('\n')
  async function copySource() {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(content)
  }

  return (
    <div className="source">
      <div className="source__toolbar">
        <span>Source excerpt</span>
        <button type="button" onClick={copySource} aria-label="Copy source excerpt">Copy source</button>
      </div>
      <pre><code>{lines.map((line, index) => (
        <span className="source__line" key={`${startLine + index}-${line}`}>
          <span className="source__number" aria-hidden="true">{startLine + index}</span>
          <span className="source__code">{line || ' '}</span>
        </span>
      ))}</code></pre>
    </div>
  )
}

function EvidenceSelector({ evidence, selectedId, onSelect }) {
  return (
    <div className="evidence-selector" role="list" aria-label="Retrieved evidence">
      {evidence.map((item, index) => (
        <div key={item.evidence_id} role="listitem">
          <button
            aria-pressed={selectedId === item.evidence_id}
            className={`evidence-selector__item ${selectedId === item.evidence_id ? 'evidence-selector__item--selected' : ''}`}
            onClick={() => onSelect(item.evidence_id)}
            type="button"
          >
            <span className="evidence-selector__index">E{String(index + 1).padStart(2, '0')}</span>
            <span className="evidence-selector__copy">
              <code>{item.file_path}</code>
              <small>{item.qualified_name} · L{item.start_line}–{item.end_line}</small>
            </span>
          </button>
        </div>
      ))}
    </div>
  )
}

function EvidenceDetail({ evidence }) {
  if (!evidence) return null
  return (
    <article className="evidence-detail">
      <header className="evidence-detail__header">
        <div className="evidence-field evidence-field--file"><span>File</span><code>{evidence.file_path}</code></div>
        <div className="evidence-field"><span>Type</span><strong>{evidence.symbol_type}</strong></div>
        <div className="evidence-field"><span>Lines</span><code>{evidence.start_line}–{evidence.end_line}</code></div>
      </header>
      <div className="evidence-symbol"><span>Symbol</span><code>{evidence.qualified_name}</code><small>Commit {evidence.commit_sha.slice(0, 7)}</small></div>
      <SourceSnippet content={evidence.content} startLine={evidence.start_line} />
    </article>
  )
}

function LoadingWorkspace() {
  return (
    <div className="query-loading" aria-label="Retrieving repository evidence" role="status">
      <div className="query-loading__answer"><span /><span /><span /></div>
      <div className="query-loading__evidence"><span /><span /><span /><span /></div>
    </div>
  )
}

export default function QueryWorkspace({ repository, snapshot, indexReady, queryState, onAsk, onNavigateRepository }) {
  const [question, setQuestion] = useState('')
  const [selectedEvidenceId, setSelectedEvidenceId] = useState(null)

  function submit(event) {
    event.preventDefault()
    const value = question.trim()
    if (value) {
      setSelectedEvidenceId(null)
      onAsk(value)
    }
  }

  if (!repository || !indexReady) {
    return (
      <section className="view intelligence-view" aria-labelledby="intelligence-title">
        <div className="view-heading"><div><p className="eyebrow">Repository intelligence</p><h1 id="intelligence-title">Intelligence</h1></div></div>
        <div className="empty-state"><span className="empty-state__code">INDEX_REQUIRED</span><h2>Repository index unavailable</h2><p>Register a repository and complete analysis before querying its source.</p><button className="button button--primary" type="button" onClick={onNavigateRepository}>Open repository setup</button></div>
      </section>
    )
  }

  const evidence = queryState.result?.evidence ?? []
  const selectedEvidence = evidence.find((item) => item.evidence_id === selectedEvidenceId) ?? evidence[0]

  return (
    <section className="view intelligence-view" aria-labelledby="intelligence-title">
      <div className="view-heading intelligence-heading"><div><p className="eyebrow">Repository intelligence</p><h1 id="intelligence-title">Query workspace</h1></div><p>Hybrid retrieval · Snapshot <code>{snapshot.commit_sha.slice(0, 7)}</code></p></div>
      <form className="query-form" onSubmit={submit}>
        <label htmlFor="repository-question">Query repository</label>
        <div className="query-form__input">
          <textarea id="repository-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Where is authentication handled and which components depend on it?" maxLength={2000} disabled={queryState.loading} />
          <div className="query-form__footer"><span>{question.length} / 2000 · Evidence-scoped response</span><button className="button button--primary" type="submit" disabled={!question.trim() || queryState.loading}>{queryState.loading ? 'Retrieving…' : 'Run query'}</button></div>
        </div>
      </form>

      {queryState.loading && <LoadingWorkspace />}
      {queryState.error && <div className="notice notice--error notice--standalone" role="alert"><strong>Query failed</strong><span>{queryState.error}</span></div>}
      {queryState.result?.outcome === 'insufficient_evidence' && <div className="notice notice--neutral notice--standalone" role="status"><strong>Insufficient evidence</strong><span>Insufficient repository evidence was retrieved for this query.</span></div>}
      {queryState.result?.outcome === 'answered' && (
        <div className="intelligence-results">
          <section className="answer-panel" aria-labelledby="response-title">
            <div className="section-label"><div><span className="panel__kicker">GENERATED ANALYSIS</span><h2 id="response-title">Response</h2></div><span>{queryState.result.cited_evidence_ids.length} citations</span></div>
            <div className="answer-panel__body">
              <p className="answer-panel__text">{queryState.result.answer}</p>
              {queryState.result.limitations.length > 0 && <div className="limitations"><strong>Limitations</strong><ul>{queryState.result.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
            </div>
          </section>
          <section className="evidence-explorer" aria-labelledby="evidence-title">
            <div className="section-label evidence-explorer__heading"><div><span className="panel__kicker">VERIFIED CONTEXT</span><h2 id="evidence-title">Evidence explorer</h2></div><span>{evidence.length} sources</span></div>
            <div className="evidence-explorer__workspace">
              <EvidenceSelector evidence={evidence} selectedId={selectedEvidence?.evidence_id} onSelect={setSelectedEvidenceId} />
              <EvidenceDetail evidence={selectedEvidence} />
            </div>
          </section>
        </div>
      )}
    </section>
  )
}
